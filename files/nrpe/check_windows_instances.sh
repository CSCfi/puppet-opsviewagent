#!/bin/bash
# Checks that instances running Windows are actually running in their designated aggregates

# Written by Matteo Pozza @ CSC 2021


## Nagios return codes
WARNING=1
#CRITICAL=2
UNKNOWN=3
OK=0

# BUSTED will contain the list of instances that have been spotted outside their designated aggregate
BUSTED=""
# NL is just an easy variable to add a carriage return to a string
NL=$'\n'

usage ()
{
  echo "Usage: $0 [OPTIONS]"
  echo " -h                 Get help"
  echo " -u <username>      OS_USERNAME"
  echo " -p <password>      OS_PASSWORD"
  echo " -a <url>           OS_AUTH_URL"
  echo " -t <project_name>  OS_TENANT_NAME"
  echo " -e <domain_name>   OS_USER_DOMAIN_NAME and OS_PROJECT_DOMAIN_NAME"
}

# if there are no args, then give help and exit
if (($# == 0)); then
  usage
  exit $UNKNOWN 
fi

# parse the args
while getopts 'hu:p:a:t:e:' OPTION
do
    case $OPTION in
        h)
            usage
            exit $UNKNOWN
            ;;
        u)
            export OS_USERNAME=$OPTARG
            ;;
        p)
            export OS_PASSWORD=$OPTARG
            ;;
        a)
            export OS_AUTH_URL=$OPTARG
            ;;
        t)
            export OS_TENANT_NAME=$OPTARG
            ;;
        e)
            export OS_USER_DOMAIN_NAME=$OPTARG
            export OS_PROJECT_DOMAIN_NAME=$OPTARG
            ;;
	    *)
            usage
            exit $UNKNOWN
            ;;
    esac
done
shift "$((OPTIND-1))"

export OS_IDENTITY_API_VERSION=3

# get the id of the aggregates whose name contains "win"
for AGG_ID in $(openstack aggregate list -c ID -c Name -f value | grep -i win | awk '{print $1}'); do
    # prepare a variable of the form "host1|host2|host3", where host1, host2, host3 are the hosts of the aggregate
    NODES_LIST=""
    for NODE in $(openstack aggregate show "$AGG_ID" -c hosts -f value | sed -e "s/\[u'//g" -e "s/ u'/ /g" -e "s/\[//g" -e "s/\]//g" -e "s/,//g"  -e "s/'//g"); do
        if [ "$NODES_LIST" = "" ]; then
            NODES_LIST="$NODE"
        else
            NODES_LIST="$NODES_LIST|$NODE"
        fi
    done
    # iterate over the projects contained in the filter_tenant_id
    for PROJ_ID in $(openstack aggregate show "$AGG_ID" -c properties -f value | grep -oE '[a-z0-9]{32}'); do
        # find instances that are running on hosts that are not the ones in the aggregate, escluding shelved instances (Host = None), and whose name or image name contain "win"
        for INSTANCE in $(openstack server list --project "$PROJ_ID" --long -c ID -c Name -c Host -c "Image Name" -f value | grep -v -E "None|$NODES_LIST" | grep -i win | awk '{print $1}'); do
            if [ "${BUSTED}" = "" ]; then
                BUSTED="$INSTANCE should be in aggregate $AGG_ID"
            else
                BUSTED="${BUSTED}${NL}$INSTANCE should be in aggregate $AGG_ID"
            fi
        done
    done
done
if [ "${BUSTED}" = "" ]; then
    echo "OK: all Windows instances are in the correct aggregates"
    exit $OK
else
    echo "WARNING: the following Windows instances are in the wrong place${NL}${BUSTED}"
    exit $WARNING
fi 
