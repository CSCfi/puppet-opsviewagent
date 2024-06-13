#!/bin/bash
#
# Rudimentary check for storcli2 based raid controllers

STATE_OK=0
STATE_WARNING=1
STATE_CRITICAL=2
STATE_UNKNOWN=3

STORCLI2_DEFAULT="/opt/MegaRAID/storcli2/storcli2"

usage ()
{
    echo "Usage: $0 [OPTIONS]"
    echo " -h                        Get help"
    echo " -p <path_to_storcli2>     Path to storcli2 binary"
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

if [ "x$STORCLI_CMD_PATH" == "x" ] ; then
    STORCLI=$STORCLI2_DEFAULT
else
    test -f $STORCLI_CMD_PATH
    if [ $? -eq 1 ] ; then
	echo "Could not find storcli at $STORCLI_CMD_PATH"
	exit ${STATE_UNKNOWN}
    fi
    STORCLI=$STORCLI_CMD_PATH
fi

output=$($STORCLI /c0 /v1  show J | jq '.["Controllers"][0]["Response Data"]["Virtual Drives"][0]["State"]')
echo "Virtual Drive state: $output"
if [ $output = '"Optl"' ] ; then
    exit ${STATE_OK}
else
    exit ${STATE_CRITICAL}
fi
