#!/usr/bin/python
#
# OpenStack Nagios/OpsView plugin to check instance and volume creation
#
# Author: Uwe Grawert

import os
import os.path
import sys
import time
import optparse
import novaclient.client as nova
from novaclient.api_versions import APIVersion
import cinderclient.exceptions
import cinderclient.v1.client as cinder
from neutronclient.neutron import client as neutronclient
import keystoneclient.v2_0.client as keystoneclient

import paramiko
import socket
import logging
import yaml
import re

# Imports for API availability checks
import glanceclient
from heatclient import client as heatclient
from magnumclient import client as magnumclient
from barbicanclient import client as barbicanclient
import novaclient
from keystoneauth1 import loading
from keystoneauth1 import session
from keystoneauth1 import identity
from keystoneclient.v3 import client as keystoneclientv3

LOCAL_DEBUG           = False
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
DEFAULT_NO_PING          = False
DEFAULT_ONLY_WINDOWS     = False

STATUS_VOLUME_AVAILABLE  = 'available'
STATUS_VOLUME_OK_DELETE  = ['available', 'error']
STATUS_INSTANCE_ACTIVE   = 'ACTIVE'
USE_SECONDS              = True

time_start = 0 # Used for timing excecution

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
  msg_fmt = "Volume is not available after creation! Status: %(status)s"

class InstanceNotAvailableException(CheckOpenStackException):
  msg_fmt = "Instance is not available after creation! Status: %(status)s"

class InstanceNotPingableException(CheckOpenStackException):
  msg_fmt = "Instance is not pingable! Status: %(status)s"

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

class VolumeErrorException(CheckOpenStackException):
  msg_fmt = "Volumes in error state %(msgs)s"

class TimeStateMachine():
  '''
  This class can be used to keep messure how long it takes to run
  a function. Example how to use:
  class OSMyFunction(TimeStateMachine):
    def long_run(self)
      sleep(10)
    def execute(self):
      long_run(self)
      b_time_ms = self.time_diff()
      long_run(self)
      c_time_ms = self.time_diff()

  '''
  time_last = time.time()

  def time_diff(self):
    now = time.time()
    diff_ms = int((now - self.time_last) * 1000)
    self.time_last = now
    return diff_ms

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

class OSInstanceCheck(TimeStateMachine):
  '''
  Create instance and destroy the instance on OpenStack
  '''
  options = dict()
  
  def __init__(self, options):
    self.options = options
    creds = OSCredentials(options).provide()
    self.nova = nova.Client(APIVersion("2.12"), **creds)

  def instance_status(self):
    instance = self.nova.servers.get(self.instance.id)
    return instance._info['status']
  
  def instance_create(self):
    image   = self.nova.images.find(name=self.options.instance_image)
    flavor  = self.nova.flavors.find(name=self.options.instance_flavor)
    network = self.nova.networks.find(label=self.options.network_name)
    self.instance = self.nova.servers.create(name=self.options.instance_name,
              image=image.id, flavor=flavor.id,
              nics=[ {'net-id': network.id} ])
  
  def instance_destroy(self):
    if hasattr(self, 'instance'):
      self.nova.servers.delete(self.instance.id)
  
  def instance_attach_floating_ip(self):
    self.fip = self.nova.floating_ips.create(self.options.fip_pool)
    self.instance.add_floating_ip(self.fip)
    
  def instance_detach_floating_ip(self):
    if hasattr(self, 'fip'):
      self.instance.remove_floating_ip(self.fip.ip)
      self.nova.floating_ips.delete(self.fip)

  def floating_ip_delete(self):
    if hasattr(self, 'fip'):
      self.nova.floating_ips.delete(self.fip)
    
  def floating_ip_ping(self):
    count = self.options.ping_count
    interval = self.options.ping_interval
    if hasattr(self, 'fip'):
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
    for instance in self.nova.servers.list(search_opts=search):
      instance.delete()

  def delete_orphaned_floating_ips(self):
    for tenant_ip in self.nova.floating_ips.list():
      self.nova.floating_ips.delete(tenant_ip)
    if len(self.nova.floating_ips.list()) != 0:
      logging.warn('All floating IPs of instance creation test tenant were not deleted.') 

  def execute(self):
    results = dict()
    try:
      self.delete_orphaned_instances()
      results['10_delete_instance_ms'] = self.time_diff()
      self.delete_orphaned_floating_ips()
      results['20_delete_floatingip_ms'] = self.time_diff()
      self.instance_create()
      results['30_create_instance_ms'] = self.time_diff()
      self.wait_instance_is_available()
      results['40_instance_available_ms'] = self.time_diff()
      if self.options.no_ping == False:
        self.instance_attach_floating_ip()
        results['50_attach_floatingip_ms'] = self.time_diff()
        self.floating_ip_ping()
        results['60_ping_instance_ms'] = self.time_diff()

    except:
      raise
    finally:
      # We suspect the ordering is important here.
      # The working assumption is that sometimes instance_destroy()
      # takes tool long or fails, and that this might break things.
      # Now we run it last.
      self.floating_ip_delete()
      results['70_delete_floatingip_ms'] = self.time_diff()
      self.instance_destroy()
      results['80_destroy_instance_ms'] = self.time_diff()
    return results


class OSGhostInstanceCheck():
  '''
  Compare instances running on compute nodes with Nova's list
  '''

  options = dict()

  def __init__(self, options):
    self.options = options
    creds = OSCredentials(options).provide()
    self.nova = nova.Client(APIVersion("2.12"), **creds)

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
    servers = self.nova.servers.list(detailed=True,search_opts=search_opts)

    instances = []

    for server in servers:
      if server.status != 'ERROR':
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
    services = self.nova.services.list(binary='nova-compute')

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
      except paramiko.SSHException as e:
        logging.warn('SSHException when connecting to {0}'.format(host))
        logging.warn('{0}: {1}'.format(e.__class__.__name__, e))
        pass

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

  def get_cinder_volume_list(self):
    search_opts = {'all_tenants': '1'}
    vols = self.volumes.list(search_opts=search_opts)
    cinderVolumes = []
    for vol in vols:
      # Some hosts look like: cloud-storagegw1@ddn1
      # We only need the hostname
      host = getattr(vol,'os-vol-host-attr:host').split('@')[0]
      cinderVolumes.append( [ vol.id.strip(), host ] )
    logging.debug(cinderVolumes)
    return cinderVolumes

  def get_cinder_volume_hosts(self):
    allHosts = self.services.list(binary='cinder-volume')
    hosts = []
    for host in allHosts:
      if host.status == 'enabled':
        # Some hosts look like: cloud-storagegw1@ddn1
        # We only need the hostname
        hosts.append(host.host.split('@')[0])

    logging.debug(hosts)
    return hosts

  def get_lvm_volume_list(self):
    '''
    ssh to all the cinder nodes and get a list of logical volumes
    '''

    ''' --option name - Print only the name of the logical volume
        --noheadings  - Omits the heading row '''
    lvsCommand = 'sudo lvs --option name --noheadings'

    hosts = self.get_cinder_volume_hosts()

    ssh = paramiko.SSHClient()

    # Load the users host keys so we can log in without password
    ssh.load_system_host_keys()

    # Automatically add host keys for new hosts
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    volumes = []

    # List the volumes on every host
    for host in hosts:
      try:
        logging.info('ssh to: ' + host)
        ssh.connect(host)
        stdin, stdout, stderr = ssh.exec_command(lvsCommand)
        for line in stdout.readlines():
          '''
          Example line:
          "  volume-baba72ac-7377-4f37-8923-a1f983bad28e"
          '''
          volumeId = line.split('-',1)[1]
          volumes.append([ volumeId, host ])
      except socket.gaierror as e:
        logging.warn('unable to connect to {0}'.format(host))
        logging.warn('{0}: {1}'.format(e.__class__.__name__, e))
        raise HostNotAvailableException(host=host)

    logging.debug(volumes)
    return volumes

  def compare_cinder_lvm_instance_lists(self):
    cinderVolumes = self.get_cinder_volume_list()
    lvmVolumes    = self.get_lvm_volume_list()

    cinderGhosts = []
    for cinderVolume in cinderVolumes:
      if not cinderVolume in lvmVolumes:
        logging.info(cinderVolume[0] + ' not found in lvs')
        cinderGhosts.append(cinderVolume)

    lvmGhosts = []
    for lvmVolume in lvmVolumes:
      if not lvmVolume in cinderVolumes:
        logging.info(lvmVolume[0] + ' not found from cinder')
        novaGhosts.append(virshInstance)
    
    if cinderGhosts or lvmGhosts:
      raise LostVolumesException(cinderGhosts=cinderGhosts,
                                 lvmGhosts=lvmGhosts)

  def execute(self):
    try:
      self.compare_cinder_lvm_instance_lists()
    except:
      raise

class OSGhostNodeCheck():
  '''
  Checks for nodes which are enabled and down
  '''

  options = dict()

  def __init__(self, options):
    self.options = options
    creds = OSCredentials(options).provide()
    self.nova = nova.Client(APIVersion("2.12"), **creds)

  def check_bad_hosts(self):
    services = self.nova.services.list()

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

class OSVolumeErrorCheck(cinder.Client):
  ''' Ghosthunting for volumes in "error " state. '''

  options = dict()

  def __init__(self, options):
    self.options = options
    creds = OSCredentials(options).provide()
    super(OSVolumeErrorCheck, self).__init__(**creds)
    self.authenticate()

  def check_volume_errors(self):

    search_opts = { 'all_tenants': '1',
                    'status': 'error',
                    'status': 'error_deleting' }
    volumes = self.volumes.list(search_opts=search_opts)
    if volumes:
      msgs = []
      for volume in volumes:
        host = getattr(volume,'os-vol-host-attr:host')
        msgs.append(' ' + volume.id + ' on ' + host)
      raise VolumeErrorException(msgs=msgs)

  def execute(self):
    try:
      self.check_volume_errors()
    except:
      raise

class OSCapacityCheck():
  '''
  Report on capacity of:
   - Number of VLANs
  '''
  options = dict()
  neutron = None

  def __init__(self, options):
    self.options = options

    ''' Keystone has different credential dict '''
    keystone_creds = OSCredentials(options).provide_keystone()
    keystone = keystoneclient.Client(**keystone_creds)
    keystone.authenticate()

    ''' Credentials for everything else '''
    creds = OSCredentials(options).provide()
    neutron_endpoint = keystone.service_catalog.url_for(service_type='network',
                                                        endpoint_type='publicURL')
    self.neutron = neutronclient.Client('2.0', endpoint_url=neutron_endpoint,
                                        token=keystone.auth_token)
    self.nova = nova.Client(APIVersion("2.12"), **creds)

  def check_network_capacity(self):
    vlan_params = { 'provider:network_type':'vlan', }
    vxlan_params = { 'provider:network_type':'vxlan', }

    vlans_in_use = len(self.neutron.list_networks(**vlan_params)['networks'])
    vxlans_in_use = len(self.neutron.list_networks(**vxlan_params)['networks'])

    # Need to find how many are available

    config = None
    # read yaml file. List if for debugging
    configFiles = [ '/var/lib/nagios/vars.yml', 'openstack/vars.yml' ]
    for configFile in configFiles:
      logging.debug('Checking: ' + configFile)
      if os.path.isfile(configFile):
        logging.debug('Found: ' + configFile)
        filehandle = open(configFile, 'r')
        config = yaml.load(filehandle)
        filehandle.close()
        break # We only care about the first matching file

    # The 'network_vlan_ranges' parameter looks like: 'default:80:89'
    # the 2nd number is the lower vlan id, the 3rd is the higher id
    # It can also look like 'default:80:89,default:65:75' so we loop over it.
    # Also, adding 1 for each range because they are inclusive.
    vlan_ranges = config['network_vlan_ranges'].split(',')
    vlans_total = 0
    for vrange in vlan_ranges:
      vlan_range = vrange.split(':')
      vlans_total = int(vlans_total) + (int(vlan_range[2]) - int(vlan_range[1])) + 1

    return { 'vlans_used': vlans_in_use, 'vlans_total': vlans_total, 'vxlans_used': vxlans_in_use }

  def check_floating_ips(self):
    # This method needs to handle the case where there are no floating ips at all

    # list_floatingips() returns a mess at the center of which is a list of
    # dictionaries about the state of each floating ip
    ips = self.neutron.list_floatingips().items()[0][1]

    # Handle the case where there are no floating ips by returning nothing
    # The rest of this method does not do any sanity checking. Use the --no-ping
    # option to totally disable floating ip capacity checking.
    if not ips: return {}

    # We need to know the ID of our 'public' router for this code. There isn't
    # a nice way to get this because customers can also reuse the same name.
    # Here we find the external network by checking what the a known csc router
    # is connected to.
    '''
    possible_router_names = ['router-nagiostest', 'nagiostest-router',
                              'nagiostest', 'csc-router']
    nagios_test_router = filter(lambda rtr: rtr['name'] in possible_router_names,
                                self.neutron.list_routers()['routers'])
    public_network_id = nagios_test_router[0]['external_gateway_info']['network_id']
    '''

    SERVICE_TENANT_NAME="service"
    PUBLIC_NET_NAME="public"
    public_network_id = self.neutron.list_networks(project_id=SERVICE_TENANT_NAME,
                         name=PUBLIC_NET_NAME)['networks'][0]['id']

    # Our public IP's are used for routers in addition to instances so we must
    # first get the total number of our public IPs assigned to ports
    ports = self.neutron.list_ports().items()[0][1]
    ports_on_public_network = filter(lambda port: port['network_id'] == public_network_id, ports)


    allocated_router = filter(lambda port: port['device_owner'] == 'network:router_gateway', ports_on_public_network)
    allocated_to_routers = len(allocated_router)

    allocated_dhcp = filter(lambda port: port['device_owner'] == 'network:dhcp', ports_on_public_network)
    allocated_to_dhcp = len(allocated_dhcp)

    # We can work out the numer of IPs used for instances using the information
    # about ports, but we can get better stats for these IP's using the
    # floating IP interface

    ''' Allocated to a tenant but not used '''
    allocated_not_assigned_ips = filter(lambda ip: ip['fixed_ip_address'] == None, ips)
    allocated_not_assigned = len(allocated_not_assigned_ips)

    ''' Allocated to a tenant and assigned to a vm '''
    allocated_and_assigned_ips = filter(lambda ip:  ip['status'] == 'ACTIVE', ips)
    allocated_and_assigned = len(allocated_and_assigned_ips)

    # Add all these together to give a simple metric for all used public IPs
    # Note: the current grafana view doesn't use this metric and instead stacks
    # all the individual values so we can see what is using the most.
    allocated_ips = allocated_not_assigned + allocated_and_assigned + \
                    allocated_to_routers + allocated_to_dhcp

    '''
    Finding a list of all the IPs configured is a complex mess

    This code assumes all our public ip subnets are /24's or smaller, but
    it wouln't be much work to make it more generic.
    '''
    # For matching IP addresses
    p = re.compile('^([0-9]+)\.([0-9]+)\.([0-9]+)\.([0-9]+)$')
    ips_total = 0

    # Get a list of the external subnets used for floating ips
    public_network = self.neutron.show_network(public_network_id)
    public_subnets = public_network[u'network']['subnets']

    # Count the number of ip's in each public subnet
    for subnet in public_subnets:
      sn = self.neutron.show_subnet(subnet)
      start_match = p.match(sn['subnet']['allocation_pools'][0]['start'])
      end_match   = p.match(sn['subnet']['allocation_pools'][0]['end'])
      if start_match:
        start_third_octet  = int(start_match.group(3))
        start_fourth_octet = int(start_match.group(4))
        end_third_octet  = int(end_match.group(3))
        end_fourth_octet = int(end_match.group(4))
        ips_total += (end_third_octet - start_third_octet) * 256 + end_fourth_octet - start_fourth_octet + 1

    return { 'ips_total': ips_total, 'ips_allocated': allocated_ips,
              'ips_allocated_not_assigned': allocated_not_assigned,
              'ips_allocated_and_assigned': allocated_and_assigned,
              'ips_allocated_to_routers': allocated_to_routers,
              'ips_allocated_to_dhcp': allocated_to_dhcp }

  def check_host_aggregate_capacities(self):
    host_aggr_capacities = dict()

    host_aggregates = self.nova.aggregates.list()
    novas = self.nova.services.list(binary='nova-compute')
    hypervisors = self.nova.hypervisors.list()
    enabled = filter(lambda srv: srv.status == 'enabled', novas)
    enabled_hosts = map(lambda x: x.host, enabled)
    enabled_hypervisors = filter(lambda x: x.service['host'] in enabled_hosts, hypervisors)

    for aggr in host_aggregates:
      # If a windows aggregate and we have not specified "only windows" then we skip it
      if "windows" in aggr.name and self.options.only_windows == False: continue
      aggr_hypervisors = filter(lambda hv: hv.hypervisor_hostname in aggr.hosts, enabled_hypervisors)

      total_aggr_cpus = sum(map(lambda hv: hv.vcpus, aggr_hypervisors))
      total_aggr_mem = sum(map(lambda hv: hv.memory_mb, aggr_hypervisors))
      used_aggr_cpus = sum(map(lambda hv: hv.vcpus_used, aggr_hypervisors))
      used_aggr_mem = sum(map(lambda hv: hv.memory_mb_used, aggr_hypervisors))

      host_aggr_capacities.update({"aggr_"+aggr.name+"_cpus_used": used_aggr_cpus,
                                    "aggr_"+aggr.name+"_mem_used": used_aggr_mem,
                                    "aggr_"+aggr.name+"_cpus_available": total_aggr_cpus,
                                    "aggr_"+aggr.name+"_mem_available": total_aggr_mem})
    return host_aggr_capacities

  def execute(self):
    results = dict()
    try:
      results.update(self.check_network_capacity())
      if self.options.no_ping == False:
        results.update(self.check_floating_ips())
      results.update(self.check_host_aggregate_capacities())
    except:
      raise
    return results


class OSCapacityCheckNetwork(OSCapacityCheck):
  def execute(self):
    results = dict()
    try:
      results.update(self.check_network_capacity())
      if self.options.no_ping == False:
        results.update(self.check_floating_ips())
    except:
      raise
    return results

class OSCapacityCheckRAM(OSCapacityCheck):
  def execute(self):
    results = dict()
    try:
      results.update(self.check_host_aggregate_capacities())
      resultsx =dict((key, value) for (key, value) in results.iteritems() if '_mem_' in key and 'aggr_' in key)
    except:
      raise
    return resultsx

class OSCapacityCheckCPUs(OSCapacityCheck):
  def execute(self):
    results = dict()
    try:
      results.update(self.check_host_aggregate_capacities())
      resultsx = dict((key, value) for (key, value) in results.iteritems() if '_cpus_' in key and 'aggr_' in key)
    except:
      raise
    return resultsx

class OSBarbicanAvailability():
  '''
  Check Barbicam API call length by using list
  '''
  options = dict()

  def __init__(self, options):
    creds = OSCredentials(options).provide_keystone()
    loader = loading.get_plugin_loader('password')
    auth = identity.V2Password(**creds)
    sessionx = session.Session(auth=auth)
    self.barbican = barbicanclient.Client(session=sessionx)


  def get_barbican_images(self):
    vols = self.barbican.secrets.list()
    if LOCAL_DEBUG:
      for i in vols:
        print i

  def execute(self):
    results = dict()
    try:
      self.get_barbican_images()
    except:
      raise


class OSCinderAvailability(cinder.Client):
  '''
  Check cinder API call length by using list volume
  '''
  options = dict()

  def __init__(self, options):
    self.options = options
    creds = OSCredentials(options).provide()
    super(OSCinderAvailability, self).__init__(**creds)
    self.authenticate()

  def get_cinder_volumes(self):
    search_opts = { }
    vols = self.volumes.list(search_opts=search_opts)
    if LOCAL_DEBUG:
      print vols

  def execute(self):
    results = dict()
    try:
      self.get_cinder_volumes()
    except:
      raise

class OSGlanceAvailability():
  '''
  Check glance API call length by using list volume
  '''
  options = dict()

  def __init__(self, options):
    creds = OSCredentials(options).provide_keystone()
    loader = loading.get_plugin_loader('password')
    auth = loader.load_from_options(**creds)
    sessionx = session.Session(auth=auth)
    self.glance = glanceclient.Client('2', session=sessionx)

  def get_glance_images(self):
    image_generator = self.glance.images.list()
    # image_generator is a generator and is layz evaluated so the
    # next is needed to acctually evaluate the image list command.
    image_generator.next()

    if LOCAL_DEBUG:
      for i in image_generator:
        i
  def execute(self):
    results = dict()
    try:
      self.get_glance_images()
    except:
      raise

class OSHeatAvailability():
  '''
  Check Heat API call length by using list heat stacks

  TODO: Create this class, this does not work yet.
  '''
  options = dict()

  def __init__(self, options):
    creds = OSCredentials(options).provide_keystone()
    loader = loading.get_plugin_loader('password')
    auth = loader.load_from_options(**creds)
    sessionx = session.Session(auth=auth)
    if LOCAL_DEBUG:
      print creds
#    self.heat = heatclient.Client('1', session=sessionx)

  def get_heat_images(self):
    vols = self.heat.stacks.list()
    vols.next()

  def execute(self):
    return {'Needs_to_be_implemented': 'heat'}
    results = dict()
    try:
      self.get_heat_images()
    except:
      raise

class OSKeystoneAvailability():
  '''
  Check Keystone API call length by creating a session
  '''
  options = dict()

  def __init__(self, options):
    creds = OSCredentials(options).provide_keystone_v3()
    auth = identity.v3.Password(**creds)
    sessionx = session.Session(auth=auth)
    self.keystone = keystoneclientv3.Client(session=sessionx)

  def get_keystone(self):
    vols = self.keystone.projects.list()

  def execute(self):
    results = dict()
    try:
      self.get_keystone()
    except:
      raise

class OSMagnumAvailability():

  '''
  Check glance API call length by using list volume
  '''
  options = dict()

  def __init__(self, options):
    creds = OSCredentials(options).provide_keystone()
    loader = loading.get_plugin_loader('password')
    auth = loader.load_from_options(**creds)
    sessionx = session.Session(auth=auth)
    self.magnum = magnumclient.Client('1', session=sessionx)

  def get_magnum_clusters(self):
    vols = self.magnum.clusters.list()
    if LOCAL_DEBUG:
      for i in vols:
        print i

  def execute(self):
    results = dict()
    try:
      self.get_magnum_clusters()
    except:
      raise

class OSNeutronAvailability():
  '''
  Check Neutron API call length by using list networks
  '''
  options = dict()

  def __init__(self, options):
    creds = OSCredentials(options).provide_keystone()
    loader = loading.get_plugin_loader('password')
    auth = loader.load_from_options(**creds)
    sessionx = session.Session(auth=auth)
    self.neutron = neutronclient.Client('2', session=sessionx)

  def get_neutron_subnetpools(self):
    vols = self.neutron.list_subnetpools()
    if LOCAL_DEBUG:
      for i in vols:
        print i

  def execute(self):
    results = dict()
    try:
      self.get_neutron_subnetpools()
    except:
      raise

class OSNovaAvailability():
  '''
  Check Nova API call length by using list volume
  '''

  options = dict()

  def __init__(self, options):
    creds = OSCredentials(options).provide_keystone()
    loader = loading.get_plugin_loader('password')
    auth = loader.load_from_options(**creds)
    sessionx = session.Session(auth=auth)
    self.nova = novaclient.client.Client('2', session=sessionx)


  def get_nova_images(self):
    vols = self.nova.servers.list()
    if LOCAL_DEBUG:
      for i in vols:
        print i

  def execute(self):
    results = dict()
    try:
      self.get_nova_images()
    except:
      raise


def parse_command_line():
  '''
  Parse command line and execute check according to command line arguments
  '''
  usage = '%prog { instance | volume | ghostinstance | ghostvolumessh | ghostvolume| ghostnodes | capacity | barbican | cinder | glance | heat | keystone | magnum | neutron | nova }'
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
  parser.add_option("-z", "--no-ping", dest='no_ping', action='store_true', help='no ping test')
  parser.add_option("-j", "--milliseconds", dest='milliseconds', action='store_true', help='Show time in milliseconds')
  parser.add_option("-k", "--only-windows", dest='only_windows', action='store_true', help='Option to only print windows aggregate OSCapacity as a way to combat 1024 character limit in check_nrpe')
  
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
  if not options.no_ping:
    options.no_ping = DEFAULT_NO_PING
  if not options.ping_count:
    options.ping_count = DEFAULT_PING_COUNT
  if not options.ping_interval:
    options.ping_interval = DEFAULT_PING_INTERVAL
  if not options.wait:
    options.wait = DEFAULT_MAX_WAIT_TIME
  if options.milliseconds:
    global USE_SECONDS
    USE_SECONDS = False
  if not options.only_windows:
    options.only_windows = DEFAULT_ONLY_WINDOWS

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
    'ghostvolumessh': OSGhostVolumeCheck,
    'ghostvolume': OSVolumeErrorCheck,
    'ghostnodes': OSGhostNodeCheck,
    'capacity': OSCapacityCheck,
    'barbican': OSBarbicanAvailability,
    'cinder': OSCinderAvailability,
    'glance': OSGlanceAvailability,
    'heat':   OSHeatAvailability,
    'magnum': OSMagnumAvailability,
    'neutron': OSNeutronAvailability,
    'nova': OSNovaAvailability,
    'keystone': OSKeystoneAvailability,
    'capacitynetwork': OSCapacityCheckNetwork,
    'capacitycpus': OSCapacityCheckCPUs,
    'capacityram': OSCapacityCheckRAM,
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

  except cinderclient.exceptions.BadRequest, e:
    print e
    exit_with_stats(NAGIOS_STATE_WARNING)
  except cinderclient.exceptions.Unauthorized, e:
    print e
    exit_with_stats(NAGIOS_STATE_UNKNOWN)
  except CredentialsMissingException, e:
    print e
    exit_with_stats(NAGIOS_STATE_UNKNOWN)
  except InstanceNotPingableException, e:
    print e
    exit_with_stats(NAGIOS_STATE_WARNING)
  except LostInstancesException as e:
    print e
    exit_with_stats(NAGIOS_STATE_WARNING)
  except HostsEnabledAndDownException as e:
    print e
    exit_with_stats(NAGIOS_STATE_WARNING)
  except HostNotAvailableException as e:
    print e
    exit_with_stats(NAGIOS_STATE_WARNING)
  except VolumeErrorException as e:
    print e
    exit_with_stats(NAGIOS_STATE_WARNING)
  #except Exception as e:
  #  print "{0}: {1}".format(e.__class__.__name__, e)
  #  exit_with_stats(NAGIOS_STATE_CRITICAL)

  exit_with_stats(NAGIOS_STATE_OK, results)

if __name__ == '__main__':
  main()
