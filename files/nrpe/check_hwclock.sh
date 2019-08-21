#!/bin/bash

# This script will check hwclock of the system.
# Then compare hwclock with system time. if there
# is more then 5 minutes of difference then it notify.

# Nagios return codes
WARNING=1
CRITICAL=2
UNKNOWN=3
OK=0

HWtime=$(sudo hwclock --debug | grep Hw | cut -d" " -f 8)
SYStime=$(date +%s)
let diff_time=$SYStime-$HWtime

if [ $diff_time -gt 900 ] ; then
   echo "Hardware clock is more than $diff_time seconds past now"
   exit $WARNING

elif [ $diff_time -lt 10 ] ; then
   echo "Hardware clock is $diff_time secound past than system time"
   exit $OK
fi
