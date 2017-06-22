#!/bin/bash
#
# Created by Sebastian Grewe, Jammicron Technology
# Changes By Jasem Elayeb on 02.03.2016
# Changes by Johan Guldmyr on 19.06.2017
# JE: add Physical Disks Name RAID_DISKS
# JE: add Physical Disks Status DISKS_STATUS
# JE: add Array Names RAID_ARRAY
# JG: add "-k" for OK on RAID_RESYNC
# JG: made RAID_DEVICES also show all of md0-md9, not just md1 and md2

# Get count of raid arrays
RAID_DEVICES=`grep ^md -c /proc/mdstat`

# Get count of degraded arrays
RAID_STATUS=`grep "\[.*_.*\]" /proc/mdstat -c`

# Is an array currently recovering, get percentage of recovery
RAID_RECOVER=`grep recovery /proc/mdstat | awk '{print $4}'`

# Is an array currently resyncing, get percentage of resync

RAID_RESYNC=`grep resync /proc/mdstat | awk '{print $4}'`

RAID_ARRAY=`awk '/md[0-9]/{for (i=1;i<=NF;++i) if ($i~/md[0-9]/)print $i}' /proc/mdstat |xargs`
RAID_DISKS=`awk '/sd[a-z]/{for (i=1;i<=NF;++i) if ($i~/sd[a-z]/)print $i}' /proc/mdstat |xargs`
DISKS_STATUS=`grep algorithm  /proc/mdstat|awk '{print $12}'`

# Check raid status
# RAID recovers --> Warning
if [[ $RAID_RECOVER ]]; then
        STATUS="WARNING - Checked $RAID_DEVICES arrays $RAID_ARRAY, recovering : $RAID_RECOVER"
	EXIT=1
# RAID resync --> Warning unless arg1 is "-k"
elif [[ $RAID_RESYNC ]]; then
        STATUS="WARNING - Checked $RAID_DEVICES arrays $RAID_ARRAY., resyncing : $RAID_RESYNC"
	if [ "$1" == "-k" ]; then
          EXIT=0
	else
	  EXIT=1
	fi
# RAID ok
elif [[ $RAID_STATUS  == "0" ]]; then
        STATUS="OK - Checked $RAID_DEVICES arrays $RAID_ARRAY."
        EXIT=0
# All else critical, better save than sorry
else
        STATUS="CRITICAL - Checked $RAID_DEVICES arrays $RAID_ARRAY, $RAID_STATUS have FAILED"
        EXIT=2
fi

# Status and quit
echo -e "$STATUS \n Physical Disks: $RAID_DISKS Disks Status: $DISKS_STATUS "
exit $EXIT
