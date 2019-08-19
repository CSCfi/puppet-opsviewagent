#!/bin/bash

# This script will check hwclock of the system.
# Then compare hwclock with system time. if there
# is more then 5 minutes of difference then it
# notify in opsview.

#!/bin/bash

HWtime=$(sudo hwclock --debug | grep Hw | cut -d" " -f 8)
SYStime=$(date +%s)
let diff_time=$SYStime-$HWtime
let diff_time_min=$diff_time/60

if [ $diff_time -gt 900 ] ; then
   echo "Hardware clock is more than $diff_time_min minutes past now"
   exit 1
fi
