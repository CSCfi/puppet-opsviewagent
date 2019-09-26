#!/bin/bash

# This script will check hwclock of the node.
# Then compare hwclock with system time.

# Nagios return codes
OK=0
WARNING=1
CRITICAL=2
UNKNOWN=3

HWtime=$(sudo hwclock --debug | grep Hw | cut -d" " -f 8)
SYStime=$(date +%s)
let diff_time=$SYStime-$HWtime

if [ $diff_time -gt 300 ] ; then
   echo "CRITICAL: Hardware clock is more than $diff_time seconds past now"
   exit $CRITICAL

elif [ $diff_time -lt 300 ] && [ $diff_time -gt 1 ] ; then
   echo "WARNING: Hardware clock is more than $diff_time seconds past now"
   exit $WARNING

elif [ $diff_time -eq 0 ] ; then
   echo "OK: Hardware clock is synced with system time"
   exit $OK

else 
   echo "Something Unknown happened here"
   exit $UNKNOWN
fi
