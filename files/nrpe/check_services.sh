#!/bin/bash

# script to check if the provided services are running
# written by Johan Guldmyr @ CSC 2013
# http://stackoverflow.com/questions/2701400/remove-first-element-from-in-bash
# http://www.linuxquestions.org/questions/linux-general-1/how-to-count-number-of-argument-received-by-a-script-201221/
# Most of the services however do require root and return code is non-zero if you ask status of a service without the proper permissions.
# Version 0.2: Added exception for rabbitmq-server to use /etc/init.d/$i and sudo.
VERSION="0.2"

# nagios return codes
OK="0"
WARN="1"
CRITICAL="2"
UNKNOWN="3"

# Set to 1 for some bonus output.
DEBUG=0

CNT=0 # This counter keeps track of how many bad services there has been.
SKIPPED=0 # Keeps track of skipped (because of insufficient permission)

SERVICE=$(which service)

# usage

usage() {
echo "check_services - a nagios script to check status of some services"
echo "Incorrect parameters, syntax example:"
echo "$0 -s service1 service2 etc"
echo "Example:"
echo "$0 -s openstack-cinder-api openstack-cinder-scheduler openstack-cinder-volume openstack-glance-api openstack-nova-conductor openstack-nova-scheduler libvirt-guests iptables mysqld restorecond"
echo "restorecond is not OK"
echo "CRITICAL: There are 1/2/10 (bad/skipped/total) services in a bad state."

}

check() {
ARGS="$#" # counting arguments sent to check()
for i in $(echo $@); do 
	EXIST="$(chkconfig --list|grep $i|wc -l)"
	if [ "$EXIST" == 0 ]; then
		# service does not exist, skipping this one.
		if [ "$DEBUG" != 0 ]; then echo "Skipping $i as it is not found in chkconfig --list."; fi
		let SKIPPED=SKIPPED+1
		continue
	else
                if [ "$i" == "rabbitmq-server" ]; then
                        STATUS="$(sudo /etc/init.d/$i status 2>&1 > /dev/null; echo $?)"
		else
			STATUS="$($SERVICE $i status 2>&1 > /dev/null; echo $?)"
		fi
		if [ "$STATUS" == 4 ]; then
			if [ "$DEBUG" != 0 ]; then echo "Skipping $i as $USER probably does not have enough privileges."; fi
			let SKIPPED=SKIPPED+1
			continue 
                elif [ "$STATUS" != "0" ]; then
                        echo "$i is not OK"
                        let CNT=CNT+1
		elif [ "$STATUS" == "0" ]; then
			if [ "$DEBUG" != 0 ]; then echo "$i is OK"; fi
			
		fi
	fi
done

}

if [ "$1" != "-s" ]; then
usage
exit 3
else
# Run the checks
	shift # remove first element of the $@ list
	check $@ # the rest elements are presumed to be services names

	if [ "$CNT" -ge 1 ]; then
		echo "CRITICAL: There are $CNT/$SKIPPED/$ARGS (bad/skipped/total) services in a bad state."
		exit $CRITICAL
	else
		echo "OK: $CNT/$SKIPPED/$ARGS (bad/skipped/total)."
		exit $OK
	fi
fi
