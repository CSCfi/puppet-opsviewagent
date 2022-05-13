#!/usr/bin/python
#
# OpenStack Nagios/OpsView plugin to check anti-affinity server group
#
# Author: Miloud Bagaa
# 

import sys
import os
import os.path
import optparse
import novaclient.client as nova
from novaclient.api_versions import APIVersion
import novaclient
from keystoneauth1 import loading
from keystoneauth1 import session
from keystoneauth1 import identity
from keystoneclient.v3 import client as keystoneclient_v3
import logging

import optparse
import os
import argparse
from collections import namedtuple

ServerGroup = namedtuple(
    'ServerGroup',
    ('id',
     'policy',
     'members_with_conflicts',
     ))

LOCAL_DEBUG           = False
NAGIOS_STATE_OK       = 0
NAGIOS_STATE_WARNING  = 1
NAGIOS_STATE_CRITICAL = 2
NAGIOS_STATE_UNKNOWN  = 3


class CheckOpenStackException(Exception):
  ''' Base Exception '''
  msg_fmt = "An unknown exception occurred."

  def __init__(self, **kwargs):
    self.message = self.msg_fmt % kwargs
  def __str__(self):
    return self.message

class CredentialsMissingException(CheckOpenStackException):
  msg_fmt = "%(key)s parameter or environment variable missing!"

class OSCredentials(object):
  '''
  Read authentication credentials from environment or optionParser
  and provide the credentials.
  '''
  cred = dict()
  keystone_cred = dict()
  keystone_v3_cred = dict()

  def __init__(self, options):
    self.environment_credentials()
    self.options_credentials(options)
    self.credentials_available()

  def environment_credentials(self):
    try:
      self.cred['auth_url']   = os.environ['OS_AUTH_URL']
      self.cred['username']   = os.environ['OS_USERNAME']
      self.cred['api_key']    = os.environ['OS_PASSWORD']
      self.cred['project_id'] = os.environ['OS_TENANT_NAME']
      # Keystone only entries
      self.keystone_cred['auth_url']    = os.environ['OS_AUTH_URL']
      self.keystone_cred['username']    = os.environ['OS_USERNAME']
      self.keystone_cred['password']    = os.environ['OS_PASSWORD']
      self.keystone_cred['tenant_name'] = os.environ['OS_TENANT_NAME']
      # Keystone v3 only entries
      self.keystone_v3_cred['auth_url']    = os.environ['OS_AUTH_URL']
      self.keystone_v3_cred['username']    = os.environ['OS_USERNAME']
      self.keystone_v3_cred['password']    = os.environ['OS_PASSWORD']
      self.keystone_v3_cred['project_name'] = os.environ['OS_TENANT_NAME']
      self.keystone_v3_cred['user_domain_name'] = os.environ['OS_USER_DOMAIN_NAME']
      self.keystone_v3_cred['project_domain_name'] = os.environ['OS_PROJECT_DOMAIN_NAME']
    except KeyError:
      pass

  def options_credentials(self, options):
    if options.auth_url: self.cred['auth_url']   = options.auth_url
    if options.username: self.cred['username']   = options.username
    if options.password: self.cred['api_key']    = options.password
    if options.tenant  : self.cred['project_id'] = options.tenant
    # Keystone only entries
    if options.auth_url: self.keystone_cred['auth_url']    = options.auth_url
    if options.username: self.keystone_cred['username']    = options.username
    if options.password: self.keystone_cred['password']    = options.password
    if options.tenant  : self.keystone_cred['tenant_name'] = options.tenant
    # Keystone v3 only entries
    if options.auth_url: self.keystone_v3_cred['auth_url']    = options.auth_url
    if options.username: self.keystone_v3_cred['username']    = options.username
    if options.password: self.keystone_v3_cred['password']    = options.password
    if options.tenant  : self.keystone_v3_cred['project_name'] = options.tenant
    if options.user_and_project_domain_name:
        self.keystone_v3_cred['user_domain_name'] = options.user_and_project_domain_name
        self.keystone_v3_cred['project_domain_name'] = options.user_and_project_domain_name
  def credentials_available(self):
    for key in ['auth_url', 'username', 'api_key', 'project_id']:
      if not key in self.cred:
        raise CredentialsMissingException(key=key)
    for key in ['auth_url', 'username', 'password', 'tenant_name']:
      if not key in self.keystone_cred:
        raise CredentialsMissingException(key=key)
    for key in ['auth_url', 'username', 'password', 'project_name', 'user_domain_name', 'project_domain_name']:
      if not key in self.keystone_v3_cred:
        raise CredentialsMissingException(key=key)

  def provide(self):
    return self.cred

  def provide_keystone(self):
    return self.keystone_cred

  def provide_keystone_v3(self):
    return self.keystone_v3_cred

def keystone_session_v3(options):
  creds = OSCredentials(options).provide_keystone_v3()
  auth = identity.v3.Password(**creds)
  sessionx = session.Session(auth=auth)
  return sessionx

class AntiAffinityChecker:
  dict_ = {}
  def __init__(self, options):
    #creds = OSCredentials(options).provide_keystone_v3()
    self.keystone_session = keystone_session_v3(options)
    self.keystone_v3 = keystoneclient_v3.Client(
        session=self.keystone_session)
    self.nova = nova.Client("2.1", session=self.keystone_session)
    self.run()

  def getCredentials(self):
    """
    Load login information from environment

    :returns: credentials
    :rtype: dict
    """
    try:
      cred = dict()
      cred['auth_url'] = os.environ.get(
        'OS_AUTH_URL').replace("v2.0", "v3")
      cred['username'] = os.environ.get('OS_USERNAME')
      cred['password'] = os.environ.get('OS_PASSWORD')
      if 'OS_PROJECT_ID' in os.environ:
        cred['project_id'] = os.environ.get('OS_PROJECT_ID')
      if 'OS_TENANT_ID' in os.environ:
        cred['project_id'] = os.environ.get('OS_TENANT_ID')
      cred['user_domain_name'] = os.environ.get(
        'OS_USER_DOMAIN_NAME', 'default')
      for key in cred:
        if not cred[key] and not PYTHON_IS_EXITING:
          print('Credentials not loaded to environment: did you load the rc file?')
          exit(1)
      return cred
    except BaseException:
      print('Credentials not loaded to environment: did you load the rc file?')
      exit(1)

  def vm_server(self, vm_id=0):
    if "vm_id" + vm_id not in self.dict_.keys():
      self.dict_["vm_id" + vm_id] = self.nova.servers.get(vm_id)
    return self.dict_["vm_id" + vm_id]

  def vm_host(self, vm_id=0):
    try:
      host = self.vm_server(vm_id).to_dict()[
          "OS-EXT-SRV-ATTR:host"]
      return host
    except BaseException:
      return None

  def vm_hypervisor_id(self, vm_id=0):
    vm_host = self.vm_host(vm_id)
    if vm_host == None:
      return None
    return self.nova.hypervisors.search(vm_host).pop().to_dict()['id']

  def run(self):
    server_group_list = []
    for server_group in self.nova.server_groups.list(all_projects=True):
      if server_group.policies[0] != "anti-affinity" and server_group.policies[0] != "soft-anti-affinity":
        continue
      hosts = {}
      for vm_id in server_group.members:
        vm_hypervisor_id = self.vm_hypervisor_id(vm_id)
        if vm_hypervisor_id is None:
          continue
        if vm_hypervisor_id not in hosts.keys():
          hosts[vm_hypervisor_id] = set([])
        hosts[vm_hypervisor_id].add(vm_id)
      for host_id in hosts.keys():
        if len(hosts[host_id]) > 1:
          server_group_list.append(
            ServerGroup(
              server_group.id,
              server_group.policies[0],
              list(hosts[vm_hypervisor_id])
            )
          )

    self.execute_check(server_group_list)

  def execute_check(self, server_group_list):

    if len(server_group_list) == 0:
      print("OK : There is no conflict")
      sys.exit(NAGIOS_STATE_OK)

    exit_code = NAGIOS_STATE_OK
    list_server_group = []
    for server_group in server_group_list:
      if server_group.policy == "anti-affinity":
        exit_code = NAGIOS_STATE_CRITICAL
        list_server_group.append(server_group.id)

    if exit_code == NAGIOS_STATE_OK:
      output = 'OK : The following server groups with soft-anti-affinity have conflicts: '
    else:
      output = 'CRITICAL : The following server groups have conflicts: '

    output = output + ", ".join(str(id) for id in list_server_group)
    print(output)
    exit(exit_code)


def main():
  '''
  Return Nagios status code
  '''
  usage = '%prog { keystone | nova }'
  parser = optparse.OptionParser(usage)
  parser.add_option("-a", "--auth_url", dest='auth_url', help='identity endpoint URL')
  parser.add_option("-u", "--username", dest='username', help='username')
  parser.add_option("-p", "--password", dest='password', help='password')
  parser.add_option("-t", "--tenant", dest='tenant', help='tenant name')
  parser.add_option("-e", "--domain", dest='user_and_project_domain_name', help='domain is used for both user_domain_name and project_domain_name, this might need to be updated in the future')
  parser.add_option("-j", "--milliseconds", dest='milliseconds', action='store_true', help='Show time in milliseconds')

  (options, args) = parser.parse_args()
  anti_affinity_checker = AntiAffinityChecker(options)

if __name__ == '__main__':
  main()

