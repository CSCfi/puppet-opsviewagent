#!/bin/bash
# Hunts for PCI devices ghosts á la nagios
#
# Ghosts show up in Newton OpenStack if one does a rebuild.
#  https://bugs.launchpad.net/nova/+bug/1780441
#
# Use case: GPUs and pci_passthrough
# Requirements:
#  - An SQL user with access to these databases.tables: 
#   - nova.pci_devices, nova.instances, nova_api.flavor_extra_specs

# Written by Johan Guldmyr @ CSC 2018

## Nagios return codes
WARNING=1
CRITICAL=2
UNKNOWN=3
OK=0

SQLPATH="/usr/local/nagios/libexec/nrpe_local/find_pci_ghosts.sql"

if [ ! -f $SQLPATH ]; then
  echo "UNKNOWN: cannot find $SQLPATH"
  exit $UNKNOWN
fi

HUNTGHOSTS="$(mysql --skip-column-names < $SQLPATH)"
# replace newlines with spaces
LISTGHOSTS="$(echo "$HUNTGHOSTS"|tr "\n" " ")"
# -n and grep -c to make this work also when there are no ghosts
COUNTGHOSTS="$(echo -n "$HUNTGHOSTS"|grep -c '^')"

if [ x"$HUNTGHOSTS" != x ]; then
  echo "CRITICAL: we found $COUNTGHOSTS instance(s) with _wrong_ amount of PCI devices: $LISTGHOSTS | ghosts=$COUNTGHOSTS"
  exit $CRITICAL
else
  echo "OK: All instances with PCI devices have same amount of PCI devices as their flavor specifies | ghosts=$COUNTGHOSTS"
  exit $OK
fi
