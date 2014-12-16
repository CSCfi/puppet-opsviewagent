#!/usr/bin/env python
#
# OpenStack Nagios/OpsView plugin to find nodes which are down:
#  - and are enabled
#  - and are running VMs
#
# Author: Peter Jenkins

import sys
import argparse
from novaclient.v1_1 import client
from novaclient import utils

STATE_OK = 0
STATE_WARNING = 1
STATE_CRITICAL = 2
STATE_UNKNOWN = 3

parser = argparse.ArgumentParser(description='Check an OpenStack Nova server for bad nodes.')
parser.add_argument('--auth_url', metavar='URL', type=str,
                    required=True,
                    help='Nova URL')
parser.add_argument('--username', metavar='username', type=str,
                    required=True,
                    help='username to use for authentication')
parser.add_argument('--password', metavar='password', type=str,
                    required=True,
                    help='password to use for authentication')
parser.add_argument('--tenant', metavar='tenant', type=str,
                    required=True,
                    help='tenant name to use for authentication')
parser.add_argument('--region_name', metavar='region_name', type=str,
                    help='Region to select for authentication')
parser.add_argument('services', metavar='SERVICE', type=str, nargs='*',
                    help='services to check for')
args = parser.parse_args()


try:
    c = client.Client(args.username,
                  args.password,
                  args.tenant,
                  args.auth_url,
                  service_type="compute")

    # This should fail if we don't have a working connection
    c.authenticate()

except Exception as e:
    print "ghostnodes: CRITICAL " + str(e)
    sys.exit(STATE_CRITICAL)

# Store any warnings or info here
msgs = []

# The servers.list() will fail unless you set a bunch of parameters
search_opts = {
            'all_tenants': True,
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

servers = c.servers.list(detailed=True,search_opts=search_opts)
hosts = []
for server in servers:
  # Sometimes the OS-EXT-SRV-ATTR:host is None, so we clean the data first
  # this might be a problem in it's own right - Peter Jenkins
  hostname = getattr(server,'OS-EXT-SRV-ATTR:host')
  if hostname != None:
    hosts.append(hostname)

# sort -u
hosts = sorted(set(hosts))

# Get a list of all the compute nodes
#services = c.services.list(binary='nova-compute')
services = c.services.list()

# Handy for debugging
#import bpdb
#bpdb.set_trace()

for service in services:
  if service.status == 'enabled' and service.state == 'down':
    msgs.append("%s on %s is enabled and down" % (service.binary,service.host))
  if service.state == 'down' and any(service.host in s for s in hosts):
    msgs.append("Node %s is running VMs and down" % service.host)

if msgs:
    print "ghostnodes: WARNING " + ", ".join(msgs)
    sys.exit(STATE_WARNING)

print "ghostnodes: OK"
sys.exit(STATE_OK)
