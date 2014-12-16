#!/bin/bash
# The Ghostbuster of Volumes
# Written by Johan Guldmyr in 2013 at CSC.
# Might be better to use python instead to interface directly with the API.
# This script requires valid nova environment variables to work.
# OS_* 
# ChangeLog:
# It also depends on the cinder client.
# 0.1: Initial Release
# 0.2: Changed critical threashold to 10 (should be a command line option)
# 
# VERSION="0.1"
### Configuration
#

# Used for naming.
CLOUD="pouta"

# States
STATE1='error ' # grep and whitespace..
STATE2="error_deleting "

# Set to anything but 0 to turn on extra output.
# Also uses a file called cinder.list in the same 
# directory as the script for input instead of cinder list --all-tenants 1.
DEBUG=0

# Security
OS_USERNAME="openstackusername"
OS_AUTH_URL="https://pouta.csc.fi:5000/v2.0"

export OS_USERNAME=$OS_USERNAME
export OS_PASSWORD='supersecretpasswordhereinsidequotes'
export OS_TENANT_NAME=$OS_USERNAME
export OS_AUTH_URL=$OS_AUTH_URL

##### End of required configuration

# Bad stuff counter
WARN_CNT=0 # Warnings
CRIT_CNT=0 # Criticals

# Nagios exit codes
OK="0"
WARNING="1"
CRITICAL="2"
UNKNOWN="3"

# Temp files
OUT_TMP="/tmp/ghost_vm_out.txt"

##### End of optional configuration

safetycheck() {

which cinder >/dev/null 2>&1
if [ $? != 0 ]; then
        echo "Could not find cinder binary in $PATH, exiting."
        exit $UNKNOWN
fi

}


ghostbuster() {

# Ghosthunting for volumes in "error " state.
if [ $DEBUG != 0 ]; then
    VOL_IN_ERROR="$(cat cinder.list|grep "error "|wc -l)"
else
    VOL_IN_ERROR="$(cinder list --all-tenants 1|grep 'error '|wc -l)"
fi

    if [ "$VOL_IN_ERROR" == 1 ]; then
        if [ $DEBUG != 0 ]; then echo "$VOL_IN_ERROR volume in $STATE1 state on $CLOUD."; fi
        let CRIT_CNT=CRIT_CNT+VOL_IN_ERROR
        cat cinder.list|grep "error "|awk '{print $2}' >> $OUT_TMP
    elif [ "$VOL_IN_ERROR" -gt 1 ]; then 
        if [ $DEBUG != 0 ]; then echo "$VOL_IN_ERROR volumes in $STATE1 state on $CLOUD."; fi
        let CRIT_CNT=CRIT_CNT+VOL_IN_ERROR
        cat cinder.list|grep "error "|awk '{print $2}' >> $OUT_TMP
    fi

# Ghosthunting for volumes in "error_deleting" state.
if [ $DEBUG != 0 ]; then
    VOL_IN_ERROR_DELETING="$(cat cinder.list|grep $STATE2|wc -l)"
else
    VOL_IN_ERROR_DELETING="$(cinder list --all-tenants 1|grep "error_deleting"|wc -l)"
fi
    if [ "$VOL_IN_ERROR_DELETING" == 1 ]; then
        if [ $DEBUG != 0 ]; then echo "$VOL_IN_ERROR_DELETING volume in $STATE2 state on $CLOUD."; fi
        let CRIT_CNT=CRIT_CNT+VOL_IN_ERROR_DELETING
        getuuids $STATE2
    elif [ "$VOL_IN_ERROR_DELETING" -gt 1 ]; then 
        if [ $DEBUG != 0 ]; then echo "$VOL_IN_ERROR_DELETING volumes in $STATE2 state on $CLOUD."; fi
        let CRIT_CNT=CRIT_CNT+VOL_IN_ERROR_DELETING
        getuuids $STATE2
    fi

}

nagiosoutput() {

if [ "$CRIT_CNT" == 1 ]; then
	echo "WARN: A ghost volume found in $CLOUD."
	cat $OUT_TMP
  cleanup
	exit $WARNING
elif [ "$CRIT_CNT" -gt 10 ]; then
	echo "CRIT: $CRIT_CNT ghost volumes found on $CLOUD."
	cat $OUT_TMP
  cleanup
  exit $CRITICAL
elif [ "$CRIT_CNT" -gt 1 ]; then
  echo "WARN: ghost volumes found in $CLOUD."
  cat $OUT_TMP
  cleanup
  exit $WARNING
else
	echo "OK: No ghost volumes found in Pouta."
	exit $OK
fi

}

getuuids() {
cinder list --all-tenants 1|fgrep $1|awk '{print $2}' >> $OUT_TMP
}

testing() {

#nova volume-list 
cat cinder.list|grep error_deleting|awk '{print $2}' >> $OUT_TMP


}

cleanup () {

rm $OUT_TMP

}

usage() {
echo "This is a nagios test hunt for volumes that are in an error state."
echo "See scriptfile for details and configuration."
}

if [ "$1" == "" ]; then
    safetycheck
	ghostbuster
	nagiosoutput
elif [ "$1" == "-t" ]; then
	testing
else
	usage
fi
