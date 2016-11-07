#!/usr/bin/python
#
# OpenStack Nagios/OpsView plugin to check utilization statistics.
# Outputs the following:
#  * Number of running VMs
#  * Number of users with at least one VM
#  * Number of CSC users with at least one VM
#  * Number of running VMs owned by CSC users
#
# Author: CSC Cloud Team

import os
import time
import sys
import optparse

from openstack_credentials import OpenStackCredentials as oscred

NAGIOS_STATE_OK       = 0
NAGIOS_STATE_WARNING  = 1
NAGIOS_STATE_CRITICAL = 2
NAGIOS_STATE_UNKNOWN  = 3

def get_all_servers(nova):
    return nova.servers.list(search_opts={'all_tenants': True})

def get_list_of_users_with_vms(nova):
    return map(lambda x: x.user_id, get_all_servers(nova))

def get_number_of_users_with_vms(nova):
    return len(set(get_list_of_users_with_vms(nova)))

def get_real_users(keystone, user_domain_name="default"):
    user_domain_id = keystone.domains.find(name=user_domain_name).id
    all_users = keystone.users.list(domain=user_domain_id)

    users = filter(lambda user: 'trng' not in user.name, all_users)
    users = filter(lambda user: hasattr(user, 'email'), users)
    users = filter(lambda user: '@localhost' not in user.email, users)

    return users

def get_vm_user_ids(nova):
    all_servers = get_all_servers(nova)
    return map(lambda x: x.user_id, all_servers)

def get_csc_user_ids(keystone, user_domain_name="default"):
    users = get_real_users(keystone, user_domain_name)
    csc_users = filter(lambda user: '@csc.fi' in user.email, users)
    return map(lambda x: x.id, csc_users)

def get_csc_user_ids_with_vms(nova, keystone, user_domain_name="default"):
    csc_vm_users = list()
    vm_user_ids = get_vm_user_ids(nova)
    csc_user_ids = get_csc_user_ids(keystone, user_domain_name)

    for user_id in vm_user_ids:
        if user_id in csc_user_ids:
            csc_vm_users.append(user_id)

    return csc_vm_users

def parse_command_line():
  '''
  Parse command line and execute check according to command line arguments
  '''
  usage = '%prog { usagestats }'
  parser = optparse.OptionParser(usage)
  parser.add_option("-a", "--auth_url", dest='auth_url', help='identity endpoint URL')
  parser.add_option("-u", "--username", dest='username', help='username')
  parser.add_option("-p", "--password", dest='password', help='password')
  parser.add_option("-i", "--project_id", dest='project_id', help='project id')
  parser.add_option("-n", "--project_name", dest='project_name', help='project name')
  parser.add_option("-o", "--auth_domain_name", dest='auth_domain_name', help='The domain of the user used for API queries.')
  parser.add_option("-d", "--user_domain_name", dest='user_domain_name', help='The domain in which the users to count are.')

  (options, args) = parser.parse_args()

  if len(args) == 0:
    sys.exit(NAGIOS_STATE_UNKNOWN, 'Command argument missing! Use --help.')

  return (options, args)

def exit_with_stats(exit_code=NAGIOS_STATE_OK, stats=dict()):
  '''
  Exits with the specified exit_code and outputs any stats in the format
  nagios/opsview expects.
  '''
  time_end = time.time() - time_start
  timing_info = {'seconds_used': int(time_end)}

  if stats:
    stats.update(timing_info)
  else:
    stats = timing_info

  if exit_code == NAGIOS_STATE_OK:
    output = 'OK |'
  elif exit_code == NAGIOS_STATE_WARNING:
    output = 'WARNING |'
  else:
    output = 'CRITICAL |'

  for key in stats:
    output += ' ' + key + '=' + str(stats[key])
  print(output)

  sys.exit(exit_code)

def main():
    global time_start
    time_start = time.time()

    results = dict()

    (options, args) = parse_command_line()

    cred = dict()
    cred['auth_url']   = options.auth_url
    cred['username']   = options.username
    cred['password']   = options.password
    cred['project_id'] = options.project_id
    cred['project_name'] = options.project_name
    cred['domain_id'] = options.auth_domain_name

    openstack = oscred(**cred)

    nova = openstack.get_nova()
    keystone = openstack.get_keystone()

    total_number_of_vms = len(get_all_servers(nova))
    users_with_vms = len(set(get_vm_user_ids(nova)))
    total_number_of_users = len(get_real_users(keystone, options.user_domain_name))
    csc_user_ids_with_vms = get_csc_user_ids_with_vms(nova, keystone, options.user_domain_name)
    num_vms_by_csc_users = len(csc_user_ids_with_vms)
    num_csc_users_with_vm = len(set(csc_user_ids_with_vms))

    results.update({"total_number_of_vms": total_number_of_vms,
                    "users_with_vms": users_with_vms,
                    "total_number_of_users": total_number_of_users,
                    "num_vms_by_csc_users": num_vms_by_csc_users,
                    "num_csc_users_with_vm": num_csc_users_with_vm}
                  )

    exit_with_stats(NAGIOS_STATE_OK, results)

if __name__ == '__main__':
  main()
