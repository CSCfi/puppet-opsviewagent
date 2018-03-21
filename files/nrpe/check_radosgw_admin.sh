#!/bin/bash

# nagios check to list users with radosgw-admin and measure how long it takes
# needs sudo permissions
# Written by Johan Guldmyr @ CSC 2018
######

RGWADMINWRAPPER="/usr/local/bin/radosgw-admin"
if [ ! -f $RGWADMINWRAPPER ]; then
  echo "UNKNOWN: Cannot find $RGWADMINWRAPPER"
  exit 3
fi

start_time="$(($(awk '/^now/ {print $3; exit}' /proc/timer_list)/1000000))"

# This is what we measure
sudo $RGWADMINWRAPPER metadata list user 2>&1 >/dev/null
RETURNCODE=$?

end_time="$(($(awk '/^now/ {print $3; exit}' /proc/timer_list
)/1000000))"
diff_time="$(($end_time - $start_time))"


if [ "$RETURNCODE" != 0 ]; then
  echo "CRITICAL: Could not list users with radosgw-admin|time=$diff_time"
  exit 2
else
  echo "OK: List users with radosgw-admin|time=$diff_time"
  exit 0
fi

