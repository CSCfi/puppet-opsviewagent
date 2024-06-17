#!/bin/bash
#
# Rudimentary check for storcli based raid controllers

STATE_OK=0
STATE_WARNING=1
STATE_CRITICAL=2
STATE_UNKNOWN=3


STORCLI_DEFAULT="/opt/MegaRAID/storcli/storcli64"
STORCLI2_DEFAULT="/opt/MegaRAID/storcli2/storcli2"

usage ()
{
    echo "Usage: $0 [OPTIONS]"
    echo " -h                        Get help"
    echo " -p <path_to_storcli>      Path to storcli binary"
}

while getopts ':p:h' OPTION
do
    case $OPTION in
        p)
            STORCLI_CMD_PATH=$OPTARG
            ;;
        h)
            usage
            exit ${STATE_UNKNOWN}
            ;;
        \?)
            usage
            exit ${STATE_UNKNOWN}
            ;;
        *)
            usage
            exit ${STATE_UNKNOWN}
            ;;
    esac
done
shift "$((OPTIND-1))"

if [ "x$STORCLI_CMD_PATH" != "x" ] ; then
    test -f $STORCLI_CMD_PATH
    if [ $? -eq 1 ] ; then
	echo "Could not find storcli at $STORCLI_CMD_PATH"
	exit ${STATE_UNKNOWN}
    fi
    STORCLI=$STORCLI_CMD_PATH
else
    test -f $STORCLI_DEFAULT
    if [ $? -eq 0 ] ; then
        STORCLI=$STORCLI_DEFAULT
    else
        test -f $STORCLI2_DEFAULT
	if [ $? -eq 0 ] ; then
            STORCLI=$STORCLI2_DEFAULT
        else
            echo "Could not find any storcli commands installed"
	    exit ${STATE_UNKNOWN}
	fi
    fi
fi

VDS=0
ERRORS=0
output=$($STORCLI /cALL /vALL  show J | jq '.["Controllers"][]["Response Data"]["Virtual Drives"][]["State"]')
for line in $output; do 
    VDS=$((VDS + 1))
    if [ $line != '"Optl"' ] ; then
        ERRORS=$((ERRORS + 1))
    fi
done
echo "$VDS Virtual Drives found $ERRORS degraded"
if [ $ERRORS -eq 0 ] ; then
    exit ${STATE_OK}
else
    exit ${STATE_CRITICAL}
fi
