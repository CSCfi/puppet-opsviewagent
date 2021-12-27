#!/usr/bin/python

import argparse
import datetime
import os
import sys

NAGIOS_STATE_OK             = 0
NAGIOS_STATE_OK_MSG         = "OK - "
NAGIOS_STATE_WARNING        = 1
NAGIOS_STATE_WARNING_MSG    = "WARNING - "
NAGIOS_STATE_CRITICAL       = 2
NAGIOS_STATE_CRITICAL_MSG   = "CRITICAL - "


def print_extra_missing_files_and_exit(extra_files, missing_files):
    global NAGIOS_STATE_CRITICAL
    global NAGIOS_STATE_CRITICAL_MSG
    if len(extra_files) > 0:
        NAGIOS_STATE_CRITICAL_MSG = NAGIOS_STATE_CRITICAL_MSG + "Extra files: "
        for filename in extra_files:
            NAGIOS_STATE_CRITICAL_MSG = NAGIOS_STATE_CRITICAL_MSG + filename + ", "
    if len(missing_files) > 0:
        NAGIOS_STATE_CRITICAL_MSG = NAGIOS_STATE_CRITICAL_MSG + "Missing files: "
        for filename in missing_files:
            NAGIOS_STATE_CRITICAL_MSG = NAGIOS_STATE_CRITICAL_MSG + filename + ", "
    print(NAGIOS_STATE_CRITICAL_MSG)
    sys.exit(NAGIOS_STATE_CRITICAL)

def main():
    parser = argparse.ArgumentParser(description='Checks that the keys folder contains all and only the expected keys')
    parser.add_argument('-m', '--max-active-keys', dest='fernet_max_active_keys', help='Max number of active keys')
    parser.add_argument('-k', '--keyrepo', dest='fernet_keyrepo', help='Path to the keys folder')
    args = parser.parse_args()
    # create a list with the names of the files we actually have in the folder
    current_files = os.listdir(args.fernet_keyrepo)
    # at least one of the files has a name that terminates with ".tmp" -> keys rotation ongoing
    for filename in current_files:
        if filename.endswith(".tmp"):
            global NAGIOS_STATE_WARNING
            global NAGIOS_STATE_WARNING_MSG
            NAGIOS_STATE_WARNING_MSG = NAGIOS_STATE_WARNING_MSG + "Key rotation ongoing"
            print(NAGIOS_STATE_WARNING_MSG)
            sys.exit(NAGIOS_STATE_WARNING)
    days_from_start = (datetime.date.today() - datetime.date(2021,1,1)).days
    # create a list with the names of the files we expect to find in the folder
    expected_files = [ str(days_from_start-i) for i in range(int(args.fernet_max_active_keys) - 1) ]
    expected_files.append(str(0))
    # check if there are files extra or missing
    extra_files = list(set(current_files).difference(set(expected_files)))
    missing_files = list(set(expected_files).difference(set(current_files)))
    if len(extra_files) > 0 or len(missing_files) > 0:
        print_extra_missing_files_and_exit(extra_files, missing_files)
    # if we are here, there are all and only the expected files in the folder
    global NAGIOS_STATE_OK
    global NAGIOS_STATE_OK_MSG
    NAGIOS_STATE_OK_MSG = NAGIOS_STATE_OK_MSG + "Keys folder contains all and only the expected keys"
    print(NAGIOS_STATE_OK_MSG)
    sys.exit(NAGIOS_STATE_OK)

if __name__ == "__main__":
    main()
