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

NAGIOS_STATE_OK       = 0
NAGIOS_STATE_WARNING  = 1
NAGIOS_STATE_CRITICAL = 2
NAGIOS_STATE_UNKNOWN  = 3

DEFAULT_INSTANCE_NAME    = 'NagiosInstanceCheck'
DEFAULT_INSTANCE_IMAGE   = 'NetBSD'
DEFAULT_INSTANCE_FLAVOR  = 'm1.tiny'
DEFAULT_INSTANCE_NETWORK = 'nagiostest'
DEFAULT_INSTANCE_FIPPOOL = 'public'
DEFAULT_VOLUME_NAME      = 'NagiosVolumeCheck'
DEFAULT_VOLUME_SIZE      = 1
DEFAULT_MAX_WAIT_TIME    = 90
DEFAULT_PING_COUNT       = 3
DEFAULT_PING_INTERVAL    = 1

STATUS_VOLUME_AVAILABLE  = 'available'
STATUS_INSTANCE_ACTIVE   = 'ACTIVE'

class CredentialsMissingException(Exception):
		'''
		OpenStack credentials missing exception
		'''
		def __init__(self, value):
				self.value = '{0} parameter or environment variable missing!'.format(value.upper())
		def __str__(self):
				return repr(self.value)

class VolumeNotAvailableException(Exception):
		'''
		OpenStack volume not available after creation
		'''
		def __init__(self, value):
				self.value = 'Volume is not available after creation! Status: {0}'.format(value)
		def __str__(self):
				return repr(self.value)

class InstanceNotAvailableException(Exception):
		'''
		OpenStack instance not available after creation
		'''
		def __init__(self, value):
				self.value = 'Instance is not available after creation! Status: {0}'.format(value)
		def __str__(self):
				return repr(self.value)

class InstanceNotPingableException(Exception):
		'''
		OpenStack instance not pingable
		'''
		def __init__(self, value):
				self.value = 'Instance is not pingable! Status: {0}'.format(value)
		def __str__(self):
				return repr(self.value)

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
								raise CredentialsMissingException(key)
		
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
				raise VolumeNotAvailableException(status)

		def execute(self):
				try:
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
				self.instance.remove_floating_ip(self.fip.ip)
				self.floating_ips.delete(self.fip)
				
		def floating_ip_ping(self):
				count = self.options.ping_count
				interval = self.options.ping_interval
				status = os.system('ping -qA -c{0} -i{1} {2}'.format(count, interval, self.fip.ip))
				if status != 0:
						raise InstanceNotPingableException(status)
				
		def wait_instance_is_available(self):
				inc = 0
				while (inc < self.options.wait):
						inc += 1
						time.sleep(1)
						status = self.instance_status()
						if status == STATUS_INSTANCE_ACTIVE:
								return
				raise InstanceNotAvailableException(status)

		def execute(self):
				try:
						self.instance_create()
						self.wait_instance_is_available()
						self.instance_attach_floating_ip()
						self.floating_ip_ping()
						self.instance_detach_floating_ip()
				except InstanceNotPingableException, e:
						self.instance_detach_floating_ip()
						raise
				except:
						raise
				finally:
						self.instance_destroy()


def parse_command_line():
		'''
		Parse command line and execute check according to command line arguments
		'''
		usage = '%prog { instance | volume }'
		parser = optparse.OptionParser(usage)
		parser.add_option("-a", "--auth_url", dest='auth_url', help='identity endpoint URL')
		parser.add_option("-u", "--username", dest='username', help='username')
		parser.add_option("-p", "--password", dest='password', help='password')
		parser.add_option("-t", "--tenant", dest='tenant', help='tenant name')

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
				parser.exit(NAGIOS_STATE_UNKNOWN, 'Command argument missing! Use --help.')
		
		return (options, args)

def execute_check(options, args):
		'''
		Execute check given as command argument
		'''
		command = args.pop()
		os_check = {
				'volume'  : OSVolumeCheck,
				'instance': OSInstanceCheck
		}

		if not command in os_check:
				parser.exit(NAGIOS_STATE_UNKNOWN, 'Unknown command argument! Use --help.')
		
		os_check[command](options).execute()

def main():
		'''
		Return Nagios status code
		'''
		try:
				(options, args) = parse_command_line()
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
		except Exception, e:
				print e
				sys.exit(NAGIOS_STATE_CRITICAL)
		
		sys.exit(NAGIOS_STATE_OK)

if __name__ == '__main__':
		main()
