#!/bin/bash
# Hunts for duplicate volume mounts  á la nagios
#
# Use case: Cinder volume multiple mounts
# Requirements:
#  - An SQL user with access to these databases.tables:
#   - nova.block_device_mapping
# Written by Johan Guldmyr @ CSC 2018
# Adapted by Chris Thomas  @ CSC 2020

## Nagios return codes
WARNING=1
CRITICAL=2
UNKNOWN=3
OK=0

SQLPATH="/usr/local/nagios/libexec/nrpe_local/find_multiattached_volumes.sql"

if [ ! -f $SQLPATH ]; then
  echo "UNKNOWN: cannot find $SQLPATH"
  exit $UNKNOWN
fi

HUNTVOLUMES="$(mysql --skip-column-names < $SQLPATH)"
# replace newlines with spaces
LISTVOLUMES="$(echo "$HUNTVOLUMES"|tr "\n" " ")"
# -n and grep -c to make this work also when there are no broken volumes
COUNTVOLUMES="$(echo -n "$HUNTVOLUMES"|grep -c '^')"

if [ x"$HUNTVOLUMES" != x ]; then
  echo "CRITICAL: we found $COUNTVOLUMES volumes(s) with _multiple_ device mappings: $LISTVOLUMES | bad_volumes=$COUNTVOLUMES"
  exit $CRITICAL
else
  echo "OK: All volumes have single mappings | bad_volumes=$COUNTVOLUMES"
  exit $OK
fi
