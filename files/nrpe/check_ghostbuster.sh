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
# The Ghostbuster
# Written by Johan Guldmyr in 2013 at CSC.
# Is a nagios/opsview check that looks for virtual machines that are not known by openstack but still running in a hypervisor.
# Might be better to use python instead to interface directly with the API.
# This script requires:
# - pdsh
# - working nova client
# Hypervisors must have hostnames of c[1-999] and be in /etc/hosts
# ChangeLog:
# 0.1: Initial Release
# 0.2: Added some safety checks (make sure $OS_ and $RUN_TMP are non-zero). Changed temp filenames to be more descriptive.
# 0.3: Also remove backup hosts from hosts file.
# 0.4: Had < and > swapped in "finding if the ghost is found with EUCA or virsh"
# 0.5: Added safety hook to check if file is world readable.
# 0.6: Improved the output to show the host name, removed the use of the EC2 commands which sometimes break
# 0.6: Handled the case where some nodes have 'None' as their hostname - Peter Jenkins
# 
VERSION="0.7"
### Configuration
## You can use the testing() function below to check out what UUID and flavors to use when booting(launching) an image(instance).
# keystone ec2-credentials-create --user-id nagiostest --tenant_id nagiostest
# keystone ec2-credentials-list
#

# Security
OS_USERNAME=""
OS_AUTH_URL="" # For example https://openstack.csc.fi:5000/v2.0

export OS_USERNAME=$OS_USERNAME
export OS_PASSWORD=''
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
RUN_TMP="/tmp/ghost_virshlist.txt"
OS_TMP="/tmp/ghost_euca.txt"
OUT_TMP="/tmp/ghost_out.txt"

##### End of optional configuration


ghostbuster() {

  # Make sure file is not readable by world (because password is in cleartext in this file)
  if [ $(find "$0" -perm -a=r) ]; then
    echo "CRITICAL: Permmisions of $0 are readable by all"
    exit $CRITICAL
  fi

  # A quick hack because our energy should be spent porting this to python
  # Get a list of hosts to check
  #HOSTS=$( nova host-list | grep compute | cut -c 3-6 | sed ':a;N;$!ba;s/\n/,/g' )
  HOSTS=$( nova service-list | grep -e nova-compute | grep "| up    |" | cut -d\  -f8 | sed ':a;N;$!ba;s/\n/,/g' )

  # Check them all
  # Both these ulgy lines cleant the horid ouput and gives:
  # c540 000025fc
  # c557 00002232
  # ...

  # Get list of all VMs according to KVM
  /usr/bin/sudo /usr/bin/pdsh -w $HOSTS virsh list --all | grep instance | \
    sed 's/\(c[[:digit:]]*\).*instance-\([[:xdigit:]]*\).*/\1 \2/' |sort -k 2 > $RUN_TMP

  # Get list of all VMs according to OpenStack
  /usr/bin/nova list --field OS-EXT-SRV-ATTR:host,OS-EXT-SRV-ATTR:instance_name --all-tenants | grep instance | \
    grep -v None | \
    sed 's/.* \(c[[:digit:]]*\).*instance-\([[:xdigit:]]*\).*/\1 \2/' | sort -k 2 > $OS_TMP

# Some safety checks:
if [ ! -s $OS_TMP ]; then
	echo "$OS_TMP is empty, could not get list of instances from nova list"
	exit $WARNING
fi
if [ ! -s $RUN_TMP ]; then
	echo "$RUN_TMP is empty, could not get list of domains from pdsh virsh list."
	exit $WARNING
fi

# Get list of all VMs according to euca2ools
DODIFF=$(diff $RUN_TMP $OS_TMP)
if [ "$?" != 0 ]; then
	let CRIT_CNT=CRIT_CNT+1
	diff $RUN_TMP $OS_TMP|grep -e "<" -e ">" > $OUT_TMP
fi

INNOVA="$(diff $RUN_TMP $OS_TMP|grep ">"|wc -l)" # counts number of extra instances in euca
INVIRS="$(diff $RUN_TMP $OS_TMP|grep "<"|wc -l)" # counts number of extra instances in virsh list 

}

nagiosoutput() {
if [ "$CRIT_CNT" != 0 ]; then
	echo "CRIT: Ghosts found in Pouta."
        if [ "$INVIRS" -gt 1 ]; then
                echo "$INVIRS instances found with virsh list that nova list could not see."
        elif [ "$INVIRS" -gt 0 ]; then
                echo "$INVIRS instance found with virsh list that nova list could not see."
        fi
        if [ "$INNOVA" -gt 1 ]; then
                echo "$INNOVA instances found with nova list that virsh list could not see."
        elif [ "$INNOVA" -gt 0 ]; then
                echo "$INNOVA instance found with nova list that virsh list could not see."
        fi
	cat $OUT_TMP
	exit $WARNING
elif [ "$CRIT_CNT" == 0 ]; then
	echo "OK: No ghosts found in Pouta."
	exit $OK
fi

}

testing() {

#$NOVA list|grep -m1 $VM|awk '{print $2} '

sudo pdsh -w c[497-576] virsh list --all | grep instance | awk '{print $3}' | cut -d- -f2 |sort -n 
#keystone tenant-list
#keystone user-list
#keystone ec2-credentials-create --user-id nagiostest --tenant_id nagiostest
#keystone ec2-credentials-list
#euca-describe-instances | grep "i-00" | awk '{print $2}' | cut -d- -f2  | sort -n

#echo pdsh -w c[$LAST-$FIRST]

}

cleanup () {

rm $RUN_TMP
rm $OS_TMP
rm $OUT_TMP

}

usage() {
echo "This is a nagios test to test an openstack instance."
echo "See scriptfile for details and configuration."
}

if [ "$1" == "" ]; then
	ghostbuster
	nagiosoutput
#	cleanup
elif [ "$1" == "-t" ]; then
	testing
else
	usage
fi
