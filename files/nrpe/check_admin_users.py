import pwd
import os
import requests
import json
import argparse

class UserChecker():
    def __init__(self, url, admingroups):
        self.url = url
        self.admingroups = admingroups
        self.rootgroup = "pouta_admins"
        self.errors = 0
        self.errorstrings = []
        self.exceptions = 0
        self.exceptionstrings = []

        self.get_users_with_login_shell()
        self.get_admin_users()
        self.get_sudoers()

        self.deployed_users = [u for u in self.all_local_users if u[0] not in self.default_users]
        self.admin_sudousers = [u for u in self.sudousers if u not in self.default_users]


    def fetch_json(self):
        try:
            response = requests.get(self.url, timeout=10)  # Set a timeout for safety
            if response.ok:
                return response.json()  # Parse JSON response
        except requests.RequestException as e:
            pass

        self.exceptions += 1
        self.exceptionstrings.append(f"Error fetching JSON")
        return None


    def get_admin_users(self):
        """ Get e.g. "pouta_admins" or "ceph_admins" """
        self.selected_admin_users = {}
        self.default_users = {}
        all_users = self.fetch_json()
        if all_users == None:
            return

        try:
            for group in self.admingroups:
                self.selected_admin_users.update(all_users[group])

            self.root_admin_users = all_users[self.rootgroup]

            self.default_users = all_users["default_allowed_users"]
        except KeyError:
            self.exceptions += 1
            self.exceptionstrings.append(f"Could not find group {group} in json")

    def get_users_with_login_shell(self):
        self.all_local_users = []
        for user in pwd.getpwall():
            if user.pw_shell not in ("/sbin/nologin", "/bin/false", "/usr/sbin/nologin"):
                self.all_local_users.append((user.pw_name, user.pw_dir))

    def check_deployed_users(self):
        deployed_usernames = set([d[0] for d in self.deployed_users])
        admin_usernames = set([ k for k in self.selected_admin_users.keys() if self.selected_admin_users[k]["state"] == "present" ] )
        self.missing_users = list(admin_usernames.difference(deployed_usernames))
        self.extra_users = list(deployed_usernames.difference(admin_usernames))

    def get_sudoers(self):
        sudofiles = os.listdir("/etc/sudoers.d")
        self.sudousers = set()
        for sudofile in sudofiles:
            with open("/etc/sudoers.d/" + sudofile, "r") as sf:
                lines = [l.strip()  for l in sf.readlines()]
                for line in lines:
                    if len(line) > 0 and line[0] != "#":
                        if line.startswith("Defaults"):
                            continue
                        sudouser = line.split(" ")[0]
                        self.sudousers.add(sudouser)

    def check_sudoers(self):
        admin_usernames = set([ k for k in self.selected_admin_users.keys() if self.selected_admin_users[k]["state"] == "present" ] )
        self.missing_sudoers = list(admin_usernames.difference(set(self.admin_sudousers)))
        self.extra_sudoers = list(set(self.admin_sudousers).difference(admin_usernames))

    def compare_keys(self, keys_actual, keys_supposed):
        try:
            keyset_actual = set([k.split(" ")[1] for k in keys_actual if len(k) > 0 and k[0] != "#"])
            keyset_supposed = set([k.split(" ")[1] for k in keys_supposed if len(k) > 0 and k[0] != "#"])
            missing_keys = list(keyset_supposed.difference(keyset_actual))
            extra_keys = list(keyset_actual.difference(keyset_supposed))
            return missing_keys, extra_keys
        except IndexError:
            self.exceptions += 1
            self.exceptionstrings.append("Error comparing ssh keys")

    def do_check(self):
        # Check user accounts
        if self.exceptions:
            return self.exceptions, self.exceptionstrings, self.errors, self.errorstrings

        self.check_deployed_users()
        user_mismatch = len(self.extra_users) + len(self.missing_users)
        if user_mismatch:
            self.errors += user_mismatch
            self.errorstrings.append(f"Missing users: {self.missing_users}, Extra users: {self.extra_users}")

        # Check admin user keys
        for user in self.deployed_users:
            if user[0] not in self.selected_admin_users:
                continue
            ssh_keyfile = os.path.join(user[1], ".ssh", "authorized_keys")

            with open(ssh_keyfile, "r") as kf:
                keys = kf.read().strip().split("\n")

            missing_k, extra_k = self.compare_keys(keys, self.selected_admin_users[user[0]]["ssh_keys"])
            error_k = len(missing_k) + len(extra_k)
            if error_k:
                self.errors += error_k
                self.errorstrings.append(f"{user[0]} Extra keys: {extra_k}, missing keys: {missing_k}")

        # Check root keys
        root_keys = []
        for ru in self.root_admin_users:
            root_keys.extend(self.root_admin_users[ru]["ssh_keys"])

        with open("/root/.ssh/authorized_keys", "r") as rf:
             root_deployed_keys = rf.read().strip().split("\n")

        missing_root_k, extra_root_k = self.compare_keys(root_deployed_keys, root_keys)

        root_k_error = len(missing_root_k) + len(extra_root_k)

        if root_k_error:
            self.errors += root_k_error
            self.errorstrings.append(f"Extra root ssh keys: {extra_root_k}, Missing root ssh keys: {missing_root_k}")

        # Check sudoers
        self.check_sudoers()
        sudo_mismatch = len(self.extra_sudoers) + len(self.missing_sudoers)
        if sudo_mismatch:
            self.errors += sudo_mismatch
            self.errorstrings.append(f"Missing sudoers: {self.missing_sudoers}, Extra sudoers: {self.extra_sudoers}")

        return self.exceptions, self.exceptionstrings, self.errors, self.errorstrings

def main():
    parser = argparse.ArgumentParser(description="Admin user verification script.")

    parser.add_argument("-g", "--group", action="append", required=True, help="Admin user group to validate, can be repeated")
    parser.add_argument("-u", "--url", required=True, help="URL for the json data")

    args = parser.parse_args()

    usercheck = UserChecker(args.url, args.group)

    exceptions, exception_str, errors, error_str = usercheck.do_check()

    if exceptions:
        print(f'Error running tool: {" ".join(exception_str)}')
        exit(3)
    if errors:
        print(" ".join(error_str))
        exit(2)
    print("OK")
    exit(0)

if __name__ == "__main__":
    main()
