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
import argparse

from openstack_credentials import OpenStackCredentials as oscred
from novaclient.exceptions import NotFound as NovaNotFound

NAGIOS_STATE_OK       = 0
NAGIOS_STATE_WARNING  = 1
NAGIOS_STATE_CRITICAL = 2
NAGIOS_STATE_UNKNOWN  = 3

def get_all_servers(nova):
    search_opts = {'all_tenants': True,
                   'deleted': False,
                   'instance_name': False}
    return nova.servers.list(search_opts=search_opts)

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

def get_vm_user_ids(servers):
    return map(lambda x: x.user_id, servers)

def get_csc_user_ids(users):
    csc_users = filter(lambda user: '@csc.fi' in user.email, users)
    return map(lambda x: x.id, csc_users)

def get_csc_user_ids_with_vms(servers, users):
    csc_vm_users = list()
    vm_user_ids = get_vm_user_ids(servers)
    csc_user_ids = get_csc_user_ids(users)

    for user_id in vm_user_ids:
        if user_id in csc_user_ids:
            csc_vm_users.append(user_id)

    return csc_vm_users

def get_hypervisor_utilization(nova):
    hv_stats = nova.hypervisor_stats.statistics()
    used_mem = hv_stats.memory_mb_used
    total_mem = hv_stats.memory_mb
    hv_util_percent = (float(used_mem) / float(total_mem)) * 100

    return (used_mem, total_mem, hv_util_percent)

def get_cinder_usage(cinder):
  search_opts = {'all_tenants': '1'}
  vols = cinder.volumes.list(search_opts=search_opts)
  cinder_usage_gb = reduce(lambda x, y: x + y.size, [0] + vols)
  return cinder_usage_gb

def get_per_flavor_active_vm_count(nova,servers):
  flavor_id_dict = dict()
  for server in servers:
    flavor = server.flavor['id']
    flavor_id_dict[flavor] = flavor_id_dict.get(flavor, 0) + 1

  flavor_name_dict = dict()
  for flavor in flavor_id_dict:
     # If the flavor have been modified the name will be missing.
     try:
       name = nova.flavors.get(flavor)
     except NovaNotFound:
       continue
     flavor_name_dict["vms." + str(name.name).replace(".", '_')] = flavor_id_dict[flavor]
  return flavor_name_dict



def parse_command_line():
  '''
  Parse command line and execute check according to command line arguments
  '''
  usage = '%prog { usagestats }'
  parser = argparse.ArgumentParser(description='Gather usage statistics from OpenStack.')
  parser.add_argument("-a", "--auth_url",
                      dest='auth_url', help='identity endpoint URL',
                      required=True)
  parser.add_argument("-u", "--username",
                      dest='username', help='username',
                      required=True)
  parser.add_argument("-p", "--password",
                      dest='password', help='password',
                      required=True)
  parser.add_argument("-i", "--project_id",
                      dest='project_id', help='project id',
                      required=True)
  parser.add_argument("-n", "--project_name",
                      dest='project_name', help='project name',
                      required=True)
  parser.add_argument("-o", "--auth_domain_name",
                      dest='auth_domain_name',
                      help="""The domain of the user used for API queries.
                           Defaults to 'default'.""",
                      required=False,
                      default="default")
  parser.add_argument("-d", "--user_domain_name",
                      dest='user_domain_name',
                      help="""The domain in which the users to count are.
                           Defaults to 'default'.""",
                      required=False,
                      default="default")

  args = parser.parse_args()

  return args

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

    options = parse_command_line()

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
    cinder = openstack.get_cinder()
    get_total_cinder_usage = get_cinder_usage(cinder)
    all_servers = get_all_servers(nova)
    all_users = get_real_users(keystone, options.user_domain_name)

    total_number_of_vms = len(all_servers)
    users_with_vms = len(set(get_vm_user_ids(all_servers)))
    total_number_of_users = len(all_users)
    csc_user_ids_with_vms = get_csc_user_ids_with_vms(all_servers, all_users)
    num_vms_by_csc_users = len(csc_user_ids_with_vms)
    num_csc_users_with_vm = len(set(csc_user_ids_with_vms))

    (used_mem, total_mem, hv_util_percent) = get_hypervisor_utilization(nova)

    results = get_per_flavor_active_vm_count(nova,all_servers)
    results.update({"total_number_of_vms": total_number_of_vms,
                    "users_with_vms": users_with_vms,
                    "total_number_of_users": total_number_of_users,
                    "num_vms_by_csc_users": num_vms_by_csc_users,
                    "num_csc_users_with_vm": num_csc_users_with_vm,
                    "hypervisor_used_mem": used_mem,
                    "hypervisor_total_mem": total_mem,
                    "hypervisor_util_percent": hv_util_percent,
                    "cinder_total_usage_gb": get_total_cinder_usage,
                   })

    exit_with_stats(NAGIOS_STATE_OK, results)

if __name__ == '__main__':
  main()
