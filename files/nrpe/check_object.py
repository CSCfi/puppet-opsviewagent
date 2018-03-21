#!/usr/bin/python
#
# OpenStack Nagios/OpsView plugin to check Object Storage Gateway
#
# Author: Johan Guldmyr

import os
import os.path
import sys
import time
import optparse
import keystoneclient.v2_0.client as keystoneclient

import socket
import logging
import yaml
import re

import urllib

# Imports for API availability checks
from swiftclient import client as swiftclient
from boto.s3.connection import S3Connection
from boto.s3.key import Key
from keystoneauth1 import loading
from keystoneauth1 import session
from keystoneauth1 import identity
from keystoneclient.v3 import client as keystoneclientv3

LOCAL_DEBUG           = False
NAGIOS_STATE_OK       = 0
NAGIOS_STATE_WARNING  = 1
NAGIOS_STATE_CRITICAL = 2
NAGIOS_STATE_UNKNOWN  = 3

DEFAULT_MAX_WAIT_TIME    = 90
DEFAULT_PING_COUNT       = 5
DEFAULT_PING_INTERVAL    = 2
DEFAULT_NO_PING          = False

USE_SECONDS              = True

time_start = 0 # Used for timing excecution

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
      self.keystone_v3_cred['user_id']    = os.environ['OS_USERNAME']
      self.keystone_v3_cred['password']    = os.environ['OS_PASSWORD']
      self.keystone_v3_cred['project_id'] = os.environ['OS_TENANT_NAME']
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
    if options.username: self.keystone_v3_cred['user_id']    = options.username
    if options.password: self.keystone_v3_cred['password']    = options.password
    if options.tenant  : self.keystone_v3_cred['project_id'] = options.tenant

  def credentials_available(self):
    for key in ['auth_url', 'username', 'api_key', 'project_id']:
      if not key in self.cred:
        raise CredentialsMissingException(key=key)
    for key in ['auth_url', 'username', 'password', 'tenant_name']:
      if not key in self.keystone_cred:
        raise CredentialsMissingException(key=key)
    for key in ['auth_url', 'user_id', 'password', 'project_id']:
      if not key in self.keystone_v3_cred:
        raise CredentialsMissingException(key=key)

  def provide(self):
    return self.cred

  def provide_keystone(self):
    return self.keystone_cred

  def provide_keystone_v3(self):
    return self.keystone_v3_cred

class OSSwiftAvailability():
  '''
  Check Swift API call length by listing containers with get_accounts
  '''
  options = dict()

  def __init__(self, options):
    creds = OSCredentials(options).provide_keystone()
    loader = loading.get_plugin_loader('password')
    auth = identity.V2Password(**creds)
    sessionx = session.Session(auth=auth)
    #self.swift = swiftclient.Connection()
    #TODO: Can one use OSCredentials??

    _authurl = creds['auth_url']
    _auth_version = 2
    _user = creds['username']
    _key = creds['password']
    _os_options = {
        'user_domain_name': "Default",
        'project_domain_name': "Default",
        'project_name': creds['tenant_name']
    }

    self.conn = swiftclient.Connection(
        authurl =_authurl,
        user =_user,
        key =_key,
        os_options =_os_options,
        auth_version =_auth_version
    )

  def get_swift_buckets(self):
    resp_headers, containers = self.conn.get_account()

    if LOCAL_DEBUG:
      for container in containers:
        print container

  def execute(self):
    results = dict()
    try:
      self.get_swift_buckets()
    except:
      raise

class S3PublicAvailability():
  '''
  Check S3 API call length by listing contents of a public bucket
  '''
  options = dict()

  def __init__(self, options):
     self.options = options
     True

  def list_public_s3_objects(self):
    """ read a public S3 URL with urllib
    """
    _response = urllib.urlopen(self.options.s3_bucket_url)
    _html = _response.read()

    if LOCAL_DEBUG:
      print _html

  def execute(self):
    try:
      self.list_public_s3_objects()
    except:
      raise

class S3PrivateAvailability():
  '''
  Check S3 API call length by listing private containers with get_accounts
  http://boto.cloudhackers.com/en/latest/s3_tut.html
  '''
  options = dict()

  def __init__(self, options):
    _access_key = options.s3_access_key
    _secret_key = options.s3_secret_key
    _s3_host = options.s3_host

    self.conn = S3Connection(aws_access_key_id=_access_key, aws_secret_access_key=_secret_key, host=_s3_host)

  def get_s3_private_buckets(self):
    all_them_buckets = self.conn.get_all_buckets()
    if LOCAL_DEBUG:
      print all_them_buckets

  def execute(self):
    results = dict()
    try:
      self.get_s3_private_buckets()
    except:
      raise

class S3FunctionalityTest():
  '''
  Functionality Test of an S3 Bucket
  '''
  options = dict()

  def __init__(self, options):
    _access_key = options.s3_access_key
    _secret_key = options.s3_secret_key
    _s3_host = options.s3_host

    self.conn = S3Connection(aws_access_key_id=_access_key, aws_secret_access_key=_secret_key, host=_s3_host)
    self.b = self.conn.get_bucket('nagiostestbucket1')
    self.k = Key(self.b)
    self.k.key = 'nagiostest1'

  def s3_create_bucket(self):
    """ create a bucket, does not fail if it exists
    """
    self.conn.create_bucket('nagiostestbucket1')

  def s3_store_data(self):
    """ store a 3MB object in the bucket
    """

    if not os.path.exists("3MBFILE"):
      with open("3MBFILE", "wb") as out:
          out.truncate(1024 * 1024 * 3)
    self.k.set_contents_from_filename("3MBFILE")

  def s3_read_data(self):
    """ read object from bucket
    """

    self.k.open()
    self.k.read()

  def s3_delete_data(self):
    """ delete object from bucket
    """

    self.k.delete()

  def execute(self):
    results = dict()
    try:
      self.s3_create_bucket()
      self.s3_store_data()
      self.s3_read_data()
      self.s3_delete_data()
    except:
      raise
    return results

###

def parse_command_line():
  '''
  Parse command line and execute check according to command line arguments
  '''
  usage = '%prog { swift | ?? }'
  parser = optparse.OptionParser(usage)
  parser.add_option("-a", "--auth_url", dest='auth_url', help='identity endpoint URL')
  parser.add_option("-u", "--username", dest='username', help='username')
  parser.add_option("-p", "--password", dest='password', help='password')
  parser.add_option("-s", "--s3_access_key", dest='s3_access_key', help='username')
  parser.add_option("-k", "--s3_secret_key", dest='s3_secret_key', help='password')
  parser.add_option("-l", "--s3_host", dest='s3_host', help='host')
  parser.add_option("-t", "--tenant", dest='tenant', help='tenant name')

  parser.add_option("-d", "--debug", dest='debug', action='store_true', help='Debug mode. Enables logging')

  parser.add_option("-b", "--s3_bucket_url", dest='s3_bucket_url', help='URL to S3 bucket')
  parser.add_option("-j", "--milliseconds", dest='milliseconds', action='store_true', help='Show time in milliseconds')

  (options, args) = parser.parse_args()

  if options.milliseconds:
    global USE_SECONDS
    USE_SECONDS = False

  if len(args) == 0:
    sys.exit(NAGIOS_STATE_UNKNOWN, 'Command argument missing! Use --help.')

  return (options, args)

def execute_check(options, args):
  '''
  Execute check given as command argument
  '''
  command = args.pop()
  os_check = {
    'swift': OSSwiftAvailability,
    's3public': S3PublicAvailability,
    's3private': S3PrivateAvailability,
    's3func': S3FunctionalityTest,
  }


  if not command in os_check:
    print 'Unknown command argument! Use --help.'
    sys.exit(NAGIOS_STATE_UNKNOWN)

  return os_check[command](options).execute()

def exit_with_stats(exit_code=NAGIOS_STATE_OK, stats=dict()):
  '''
  Exits with the specified exit_code and outputs any stats in the format
  nagios/opsview expects.
  '''
  time_end = time.time() - time_start
  if USE_SECONDS:
    timing_info = {'seconds_used': int(time_end)}
  else:
    timing_info = {'milliseconds_used': int(1000 * time_end)}

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
  '''
  Return Nagios status code
  '''

  global time_start
  time_start = time.time()

  results = dict()

  try:
    (options, args) = parse_command_line()
    if options.debug:
      logging.basicConfig(level=logging.DEBUG)

    # Call the check
    results = execute_check(options, args)

  except Exception as e:
    print "{0}: {1}".format(e.__class__.__name__, e)
    exit_with_stats(NAGIOS_STATE_CRITICAL)

  exit_with_stats(NAGIOS_STATE_OK, results)

if __name__ == '__main__':
  main()
