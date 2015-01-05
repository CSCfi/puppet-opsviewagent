#!/usr/bin/python
#
# OpenStack Nagios/OpsView plugin to check instance and volume creation
#
# Author: Uwe Grawert

import os
import sys
import time
import optparse
import novaclient.v1_1.client as nova
import cinderclient.exceptions
import cinderclient.v1.client as cinder

import paramiko
import socket
import logging

NAGIOS_STATE_OK       = 0
NAGIOS_STATE_WARNING  = 1
NAGIOS_STATE_CRITICAL = 2
NAGIOS_STATE_UNKNOWN  = 3

DEFAULT_INSTANCE_NAME    = 'NagiosInstanceCheck'
DEFAULT_INSTANCE_IMAGE   = 'cirros-0.3.0-x86_64'
DEFAULT_INSTANCE_FLAVOR  = 'm1.tiny'
DEFAULT_INSTANCE_NETWORK = 'nagiostest'
DEFAULT_INSTANCE_FIPPOOL = 'public'
DEFAULT_VOLUME_NAME      = 'NagiosVolumeCheck'
DEFAULT_VOLUME_SIZE      = 1
DEFAULT_MAX_WAIT_TIME    = 90
DEFAULT_PING_COUNT       = 5
DEFAULT_PING_INTERVAL    = 2

STATUS_VOLUME_AVAILABLE  = 'available'
STATUS_VOLUME_OK_DELETE  = ['available', 'error']
STATUS_INSTANCE_ACTIVE   = 'ACTIVE'

class CheckOpenStackException(Exception):
  ''' Base Exception '''
  msg_fmt = "An unknown exception occurred."

  def __init__(self, **kwargs):
    self.message = self.msg_fmt % kwargs
  def __str__(self):
    return self.message

class CredentialsMissingException(CheckOpenStackException):
  msg_fmt = "%(key)s parameter or environment variable missing!"

class VolumeNotAvailableException(CheckOpenStackException):
  msg_fmt = "Volume is not available after creation! Status: %(status)d"

class InstanceNotAvailableException(CheckOpenStackException):
  msg_fmt = "Instance is not available after creation! Status: %(status)d"

class InstanceNotPingableException(CheckOpenStackException):
  msg_fmt = "Instance is not pingable! Status: %(status)d"

class HostNotAvailableException(CheckOpenStackException):
  msg_fmt = "Unable to ssh to %(host)s"

class HostNotAvailableException(CheckOpenStackException):
  msg_fmt = "Unable to ssh to %(host)s"

class HostsEnabledAndDownException(CheckOpenStackException):
  msg_fmt = "Nova hosts enabled and down: %(msgs)s"

class LostInstancesException(CheckOpenStackException):
  msg_fmt = "Instances missing from nodes %(virshGhosts)s \n" + \
            "Instances missing from nova  %(novaGhosts)s"

class LostVolumesException(CheckOpenStackException):
  msg_fmt = "Volumes missing from storage %(lvmGhosts)s \n" + \
            "Volumes missing from cinder  %(cinderGhosts)s \n"

class OSCredentials(object):
  '''
  Read authentication credentials from environment or optionParser
  and provide the credentials.
  '''
  cred = dict()
  
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
    except KeyError:
      pass

  def options_credentials(self, options):
    if options.auth_url: self.cred['auth_url']   = options.auth_url
    if options.username: self.cred['username']   = options.username
    if options.password: self.cred['api_key']    = options.password
    if options.tenant  : self.cred['project_id'] = options.tenant

  def credentials_available(self):
    for key in ['auth_url', 'username', 'api_key', 'project_id']:
      if not key in self.cred:
        raise CredentialsMissingException(key=key)
  
  def provide(self):
    return self.cred

class OSVolumeCheck(cinder.Client):
  '''
  Create cinder volume and destroy the volume on OpenStack
  '''
  options = dict()
  
  def __init__(self, options):
    self.options = options
    creds = OSCredentials(options).provide()
    super(OSVolumeCheck, self).__init__(**creds)
    self.authenticate()

  def volume_create(self):
    self.volume = self.volumes.create(display_name=self.options.volume_name,
              size=self.options.volume_size)

  def volume_destroy(self):
    if hasattr(self, 'volume'):
      self.volume.delete()
  
  def volume_status(self):
    volume = self.volumes.get(self.volume.id)
    return volume._info['status']

  def wait_volume_is_available(self):
    inc = 0
    while (inc < self.options.wait):
      inc += 1
      time.sleep(1)
      status = self.volume_status()
      if status == STATUS_VOLUME_AVAILABLE:
        return
    raise VolumeNotAvailableException(status=status)

  def delete_orphaned_volumes(self):
    search = dict(display_name = self.options.volume_name)
    for volume in self.volumes.list(search_opts=search):
      if volume._info['status'] in STATUS_VOLUME_OK_DELETE:
        volume.delete()

  def execute(self):
    try:
      self.delete_orphaned_volumes()
      self.volume_create()
      self.wait_volume_is_available()
    except:
      raise
    finally:
      self.volume_destroy()

class OSInstanceCheck(nova.Client):
  '''
  Create instance and destroy the instance on OpenStack
  '''
  options = dict()
  
  def __init__(self, options):
    self.options = options
    creds = OSCredentials(options).provide()
    super(OSInstanceCheck, self).__init__(**creds)
    self.authenticate()

  def instance_status(self):
    instance = self.servers.get(self.instance.id)
    return instance._info['status']
  
  def instance_create(self):
    image   = self.images.find(name=self.options.instance_image)
    flavor  = self.flavors.find(name=self.options.instance_flavor)
    network = self.networks.find(label=self.options.network_name)
    self.instance = self.servers.create(name=self.options.instance_name,
              image=image.id, flavor=flavor.id,
              nics=[ {'net-id': network.id} ])
  
  def instance_destroy(self):
    if hasattr(self, 'instance'):
      self.servers.delete(self.instance.id)
  
  def instance_attach_floating_ip(self):
    self.fip = self.floating_ips.create(self.options.fip_pool)
    self.instance.add_floating_ip(self.fip)
    
  def instance_detach_floating_ip(self):
    if hasattr(self, 'fip'):
      self.instance.remove_floating_ip(self.fip.ip)
      self.floating_ips.delete(self.fip)

  def floating_ip_delete(self):
    if hasattr(self, 'fip'):
      self.floating_ips.delete(self.fip)
    
  def floating_ip_ping(self):
    count = self.options.ping_count
    interval = self.options.ping_interval
    status = os.system('ping -qA -c{0} -i{1} {2}'.format(count, interval, self.fip.ip))
    if status != 0:
      raise InstanceNotPingableException(status=status)
    
  def wait_instance_is_available(self):
    inc = 0
    while (inc < self.options.wait):
      inc += 1
      time.sleep(1)
      status = self.instance_status()
      if status == STATUS_INSTANCE_ACTIVE:
        return
    raise InstanceNotAvailableException(status=status)
  
  def delete_orphaned_instances(self):
    search = dict(name = self.options.instance_name)
    for instance in self.servers.list(search_opts=search):
      instance.delete()

  def execute(self):
    try:
      self.delete_orphaned_instances()
      self.instance_create()
      self.wait_instance_is_available()
      self.instance_attach_floating_ip()
      self.floating_ip_ping()
    except:
      raise
    finally:
      self.instance_destroy()
      self.floating_ip_delete()

class OSGhostInstanceCheck(nova.Client):
  '''
  Compare instances running on compute nodes with Nova's list
  '''

  options = dict()

  def __init__(self, options):
    self.options = options
    creds = OSCredentials(options).provide()
    super(OSGhostInstanceCheck, self).__init__(**creds)
    self.authenticate()

  def get_nova_instance_list(self):

    # The servers.list() will fail unless you set a bunch of parameters
    search_opts = {'all_tenants': True,
                   'reservation_id': None,
                   'ip': None,
                   'ip6': None,
                   'name': None,
                   'image': None,
                   'flavor': None,
                   'status': None,
                   'tenant_id': None,
                   'host': None,
                   'deleted': False,
                   'instance_name': False}

    # Get the array of Server objects
    servers = self.servers.list(detailed=True,search_opts=search_opts)

    instances = []

    for server in servers:
      hostname = getattr(server,'OS-EXT-SRV-ATTR:host')
      instance = getattr(server,'OS-EXT-SRV-ATTR:instance_name')
      # Sometimes the OS-EXT-SRV-ATTR:host is None, so we clean the data first
      # this might be a problem in it's own right - Peter Jenkins
      if hostname != None:
        instances.append([instance, hostname])
      else:
        logging.warn(server.id + ' has no host atribute')

    return instances

  def get_nova_host_list(self):
    services = self.services.list(binary='nova-compute')

    hosts = []

    for service in services:
      # Check all the nova-compute nodes that are up (included disabled hosts)
      if service.state == 'up':
        hosts.append(service.host)

    return hosts

  def get_virsh_instance_list(self):
    '''
    ssh to every host, check the vms running with virsh list
    '''
    
    # --all shows all vms not just the running ones
    # --name omits the table headers just prints a list of vm names
    virshList = 'sudo virsh list --all --name'

    hosts = self.get_nova_host_list()

    ssh = paramiko.SSHClient()

    # Load the users host keys so we can log in without password
    ssh.load_system_host_keys()

    # Automatically add host keys for new hosts
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    instances = []

    # List the vms on every host
    for host in hosts:
      try:
        logging.info('ssh to: ' + host)
        ssh.connect(host)
        stdin, stdout, stderr = ssh.exec_command(virshList)
        for line in stdout.readlines():
          instance = line.strip()
          # Last line is always empty
          if len(instance) > 0:
            instances.append([line.strip(), host])
      except socket.gaierror as e:
        logging.warn('unable to connect to {0}'.format(host))
        logging.warn('{0}: {1}'.format(e.__class__.__name__, e))
        raise HostNotAvailableException(host=host)

    return instances

  def compare_nova_virsh_instance_lists(self):
    '''
    Compare both lists of hosts and report any differences
    '''
    novaInstances = self.get_nova_instance_list()
    virshInstances = self.get_virsh_instance_list()

    virshGhosts = []
    for novaInstance in novaInstances:
      if not novaInstance in virshInstances:
        logging.info(novaInstance[0] + ' not found in virsh list')
        virshGhosts.append(novaInstance)

    novaGhosts = []
    for virshInstance in virshInstances:
      if not virshInstance in novaInstances:
        logging.info(virshInstance[0] + ' not found from nova')
        novaGhosts.append(virshInstance)
    
    if virshGhosts or novaGhosts:
      raise LostInstancesException(virshGhosts=virshGhosts,
                                   novaGhosts=novaGhosts)

  def execute(self):
    try:
      self.compare_nova_virsh_instance_lists()
    except:
      raise

class OSGhostVolumeCheck(cinder.Client):
  options = dict()

  def __init__(self, options):
    self.options = options
    creds = OSCredentials(options).provide()
    super(OSGhostVolumeCheck, self).__init__(**creds)
    self.authenticate()

  def execute(self):
    try:
      self.check_bad_hosts()
    except:
      raise

class OSGhostNodeCheck(nova.Client):
  '''
  Checks for nodes which are enabled and down
  '''

  options = dict()

  def __init__(self, options):
    self.options = options
    creds = OSCredentials(options).provide()
    super(OSGhostNodeCheck, self).__init__(**creds)
    self.authenticate()

  def check_bad_hosts(self):
    services = self.services.list()

    msgs = []

    for service in services:
      if service.status == 'enabled' and service.state == 'down':
        msgs.append("%s on %s, " % (service.binary,service.host))

    if msgs:
      raise HostsEnabledAndDownException(msgs=msgs)
    else:
      logging.info('No enabled hosts are down')
  
  def execute(self):
    try:
      self.check_bad_hosts()
    except:
      raise

def parse_command_line():
  '''
  Parse command line and execute check according to command line arguments
  '''
  usage = '%prog { instance | volume | ghostinstance | ghostvolume | ghostnodes }'
  parser = optparse.OptionParser(usage)
  parser.add_option("-a", "--auth_url", dest='auth_url', help='identity endpoint URL')
  parser.add_option("-u", "--username", dest='username', help='username')
  parser.add_option("-p", "--password", dest='password', help='password')
  parser.add_option("-t", "--tenant", dest='tenant', help='tenant name')

  parser.add_option("-d", "--debug", dest='debug', action='store_true', help='Debug mode. Enables logging')

  parser.add_option("-i", "--instance_name", dest='instance_name', help='instance name')
  parser.add_option("-f", "--instance_flavor", dest='instance_flavor', help='flavour name')
  parser.add_option("-m", "--instance_image", dest='instance_image', help='image name')
  parser.add_option("-n", "--network_name", dest='network_name', help='network name')
  parser.add_option("-l", "--floating_ip_pool", dest='fip_pool', help='floating ip pool name')
  parser.add_option("-c", "--ping_count", dest='ping_count', help='number of ping packets')
  parser.add_option("-I", "--ping_interval", dest='ping_interval', help='seconds interval between ping packets')
  
  parser.add_option("-v", "--volume_name", dest='volume_name', help='test volume name')
  parser.add_option("-s", "--volume_size", dest='volume_size', help='test volume size')
  parser.add_option("-w", "--wait", dest='wait', type='int', help='max seconds to wait for creation')
  
  (options, args) = parser.parse_args()

  if not options.volume_name:
    options.volume_name = DEFAULT_VOLUME_NAME
  if not options.volume_size:
    options.volume_size = DEFAULT_VOLUME_SIZE
  if not options.instance_name:
    options.instance_name = DEFAULT_INSTANCE_NAME
  if not options.instance_flavor:
    options.instance_flavor = DEFAULT_INSTANCE_FLAVOR
  if not options.instance_image:
    options.instance_image = DEFAULT_INSTANCE_IMAGE
  if not options.network_name:
    options.network_name = DEFAULT_INSTANCE_NETWORK
  if not options.fip_pool:
    options.fip_pool = DEFAULT_INSTANCE_FIPPOOL
  if not options.ping_count:
    options.ping_count = DEFAULT_PING_COUNT
  if not options.ping_interval:
    options.ping_interval = DEFAULT_PING_INTERVAL
  if not options.wait:
    options.wait = DEFAULT_MAX_WAIT_TIME

  if len(args) == 0:
    sys.exit(NAGIOS_STATE_UNKNOWN, 'Command argument missing! Use --help.')
  
  return (options, args)

def execute_check(options, args):
  '''
  Execute check given as command argument
  '''
  command = args.pop()
  os_check = {
    'volume'  : OSVolumeCheck,
    'instance': OSInstanceCheck,
    'ghostinstance': OSGhostInstanceCheck,
    'ghostvolume': OSGhostVolumeCheck,
    'ghostnodes': OSGhostNodeCheck
  }


  if not command in os_check:
    print 'Unknown command argument! Use --help.'
    sys.exit(NAGIOS_STATE_UNKNOWN)
  
  os_check[command](options).execute()

def main():
  '''
  Return Nagios status code
  '''

  time_start = time.time()

  try:
    (options, args) = parse_command_line()
    if options.debug:
      logging.basicConfig(level=logging.INFO)

    execute_check(options, args)
  except cinderclient.exceptions.BadRequest, e:
    print e
    sys.exit(NAGIOS_STATE_WARNING)
  except cinderclient.exceptions.Unauthorized, e:
    print e
    sys.exit(NAGIOS_STATE_UNKNOWN)
  except CredentialsMissingException, e:
    print e
    sys.exit(NAGIOS_STATE_UNKNOWN)
  except InstanceNotPingableException, e:
    print e
    sys.exit(NAGIOS_STATE_WARNING)
  except LostInstancesException as e:
    print e
    sys.exit(NAGIOS_STATE_WARNING)
  except HostsEnabledAndDownException as e:
    print e
    sys.exit(NAGIOS_STATE_WARNING)
  #except Exception as e:
  #  print "{0}: {1}".format(e.__class__.__name__, e)
  #  sys.exit(NAGIOS_STATE_CRITICAL)
  except HostNotAvailableException as e:
    print e
    
  time_end = time.time() - time_start

  print '----'
  print 'OK | seconds used={0}'.format(int(time_end))
  sys.exit(NAGIOS_STATE_OK)

if __name__ == '__main__':
  main()
