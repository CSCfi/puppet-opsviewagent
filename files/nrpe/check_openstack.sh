#!/bin/bash
####
#The MIT License (MIT)
#
#Copyright (c) [2014] [Johan Guldmyr]
#
#Permission is hereby granted, free of charge, to any person obtaining a copy
#of this software and associated documentation files (the "Software"), to deal
#in the Software without restriction, including without limitation the rights
#to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#copies of the Software, and to permit persons to whom the Software is
#furnished to do so, subject to the following conditions:
#
#The above copyright notice and this permission notice shall be included in all
#copies or substantial portions of the Software.
#
#THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#SOFTWARE.
####

# Written by Johan Guldmyr as a proof of concept in 2013 at CSC.
# Modified by Risto Laurikainen in 2014 at CSC (v0.4).
# It is a nagios script that tests basic openstack functionality and it: starts, adds a floating IP, pings and then terminates a virtual machine.
# Might be better to use python instead to interface directly with the API to not be depending on possibly changing output of some CLI tools.
# This script requires valid nova environment variables to work.
# OS_USERNAME, OS_PASSWORD, OS_TENANT_NAME, OS_AUTH_URL
# ChangeLog:
# 0.1: Initial Release
# 0.2: Complete re-write. Made it launch, ping and terminate an instance.
# 0.3: Added more details about settings and added safety hook to not run script if it's world readable.
# 0.4: Changed handling of parameters. They are now retrieved using getops instead of hardcoding.
#      Removed some Pouta specific UUIDs from the comments.
#      As there are no passwords in this file anymore, it can be set world readable. Removed the hook that checks this.
#      Improved floating IP allocation to be more generic and less fragile.
#
# VERSION="0.4"
### Configuration
## You can use the testing() function below to check out what UUID and flavors to use when booting(launching) an image(instance).

###### Start of configuration

while getopts ":v:i:f:k:n:u:p:U:P:" option; do
    case $option in
        v) VM=$OPTARG;;
        i) VM_IMAGE_UUID=$OPTARG;;
        f) FLAVOR=$OPTARG;;
        k) KEY_NAME=$OPTARG;;
        n) NET_ID=$OPTARG;;
        u) OS_USERNAME=$OPTARG;;
        p) OS_TENANT_NAME=$OPTARG;;
        U) OS_AUTH_URL=$OPTARG;;
        P) OS_PASSWORD=$OPTARG;;
        \?) echo "Invalid argument: -$OPTARG" >&2 ; exit 3;;
        :) echo "Must provide an argument with -$OPTARG" >&2 ; exit 3;;
    esac
done

set -u

export OS_USERNAME=$OS_USERNAME
export OS_TENANT_NAME=$OS_TENANT_NAME
export OS_AUTH_URL=$OS_AUTH_URL
export OS_PASSWORD=$OS_PASSWORD

# Some optional settings:
DEBUG="0" # Set to something larger than 0 for extra output.
WAITINT="10" # WAITING x 2 = How long to wait after launching an instance before trying to ping.
PINGATTEMPTS=20 # How many times to ping before stopping.

##### End of Configuration

# Find nova binary, probably somewhat redundant.
which nova 2>&1 > /dev/null
if [ $? != 0 ]; then NOVA="/usr/bin/nova"; else NOVA=$(which nova); fi

# Bad stuff counter
WARN_CNT=0 # Warnings
CRIT_CNT=0 # Criticals

# Nagios exit codes
OK="0"
WARNING="1"
CRITICAL="2"
UNKNOWN="3"

# Capture error codes
NOSTART=0
NOLIST=0
NOPING=0
NOSTOP=0

safety() {

# Check if there already is a VM called $VM and if so delete it.
if [ "$($NOVA list|grep $VM|wc -l 2>&1)" -gt 0 ]; then
	UPDATETIME="$($NOVA show $VM|grep updated|awk '{print $4}'|sed -e 's/T/ /'| sed -e 's/Z//')"
	UPDATETIMEINEPOCH="$(date -d "$UPDATETIME" +%s)"
	CURRENTTIMEINEPOCH="$(date +%s)"
	CURRM15=$(( $CURRENTTIMEINEPOCH-10 ))
	if [ $CURRM15 -lt $UPDATETIMEINEPOCH ]; then
		echo "CRIT: Test ran within 10s after $VM was updated ($UPDATETIME)."
		let CRIT_CNT=CRIT_CNT+1
	fi
	if [ "$DEBUG" != 0 ]; then
		echo $UPDATETIMEINEPOCH
		echo $CURRENTTIMEINEPOCH
		echo $CURRM15
	fi

	# delete it
	let WARN_CNT=WARN_CNT+1
	terminateinstance
	echo "WARN: VM $VM was already running, deleted it."
	nagiosoutput
fi

}

launchinstance() {

if [ "$DEBUG" != "0" ]; then 
	echo "#### launchinstance"
	echo "Sending: $NOVA boot --flavor $FLAVOR --image $VM_IMAGE_UUID --key-name $KEY_NAME --nic net-id=$NET_ID $VM"
fi

$NOVA boot --flavor $FLAVOR --image $VM_IMAGE_UUID --key-name "$KEY_NAME" --nic net-id=$NET_ID $VM 2>&1 >/dev/null
if [ "$?" == 0 ]; then 
	if [ "$DEBUG" != 0 ]; then echo "Started $VM"; fi
else
	echo "CRIT: Could not start $VM."
	let CRIT_CNT=CRIT_CNT+1
	exit $CRITICAL
fi

}

floatingIP() {
if [ "$DEBUG" != "0" ]; then echo "#### floatingIPPING"; fi
# Add a floating IP
THEIP="$($NOVA floating-ip-list|grep "public"|awk '{print $2}'|head -n 1)" # grab the first IP in the list
$NOVA add-floating-ip $VM $THEIP
if [ "$?" != 0 ]; then 
	let CRIT_CNT=CRIT_CNT+1 
	if [ "$DEBUG" != 0 ]; then
		echo "CRIT:Could not assign $THEIP to $VM"
	fi
fi # increase critical counter

COULDPING=0
COUNTER=0
while [ $COULDPING -lt 1 ]; do

	if [ "$(ping -W 1 -q -c1 $THEIP 2>&1 >/dev/null; echo $?)" != "0" ]; then
		if [ "$DEBUG" != 0 ]; then 
			echo "Could not ping VM $VM with IP $THEIP from `hostname`"
		fi
	
		let COUNTER=COUNTER+1
		if [ "$COUNTER" -gt $PINGATTEMPTS ]; then 
			if [ "$DEBUG" != 0 ]; then 
				echo "WARN: Could not ping $VM ($THEIP) within ~$COUNTER seconds."
				# Time = 2x$COUNTER ?
			fi
			echo "CRIT: Could not ping $VM ($THEIP)."
			CRIT_CNT=CRIT_CNT+1
			COULDPING=1 # exit the loop
		fi
		sleep 4
	else
		if [ "$DEBUG" != 0 ]; then
			echo "Could ping $THEIP ~$COUNTER seconds after allocating."
		fi
		COULDPING=1 # and leave the loop
	fi

done

# Remove the floating IP
$NOVA remove-floating-ip $VM $THEIP
if [ "$?" != 0 ]; then
	echo "WARN: Could not remove $THEIP from $VM"
	WARN_CNT=WARN_CNT+1
fi

}

terminateinstance() {
if [ "$DEBUG" != "0" ]; then echo "#### terminateinstance"; fi

if [ "$DEBUG" != 0 ]; then echo "$NOVA delete $VM"; fi
	$NOVA delete $VM
	# On non-existing and multiple VM "nova delete" still gives RC 0
	LISTVMS="$($NOVA list|grep $VM|wc -l)"
	if [ "$LISTVMS" -gt 1 ]; then
		CRIT_CNT=CRIT_CNT+1
		GETFIRSTVMUUID="$($NOVA list|grep -m1 $VM|awk '{print $2}')"
		$NOVA delete $GETFIRSTVMUUID
		echo "CRIT: More than one VM called $VM found, terminated first."
	fi

}

nagiosoutput() {

if [ "$CRIT_CNT" != 0 ]; then
	if [ "$DEBUG" != 0 ]; then
		# Possibly redundany info below
		echo "CRIT: Problem starting/stopping VM $VM on pouta."
	fi
	exit $CRITICAL
elif [ "$CRIT_CNT" == 0 ]; then
	if [ "$WARN_CNT" != 0 ]; then
		# Wherever $WARN_CNT is increased some message is already included.
		exit $WARNING
	fi
	echo "OK: Could launch, ping(public IP) and terminate instance $VM on $OS_AUTH_URL."
	exit $OK
fi

}

testing() {

$NOVA flavor-list

}

usage() {
echo "This is a nagios test to test an openstack instance."
echo "See scriptfile for details and configuration."
}

if (( $# == 18 )); then
safety
launchinstance
sleep $WAITINT
floatingIP
terminateinstance
nagiosoutput
elif [ "$1" == "-d" ]; then
terminateinstance
elif [ "$1" == "-t" ]; then
testing
else
usage
fi
