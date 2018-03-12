#!/bin/bash
#
# Check with which Multi-Exit Discriminator value Service IPs are announced
# from ExaBGP, based on a log file.

set -e

STATE_OK=0
STATE_WARNING=1
STATE_CRITICAL=2
STATE_UNKNOWN=3

# Opportunism.
TAIL_LINES=1000

usage ()
{
    echo "Usage: $0 [OPTIONS]"
    echo " -h               Get help"
    echo " -f               Log file to inspect"
    # echo " -a <address>     Address whose MED to check"
}

if (($# == 0)); then
  usage
  exit 1
fi

while getopts ':f:a:h' OPTION
do
    case $OPTION in
        h)
            usage
            exit 0
            ;;
        f)
            LOG_FILE_NAME=$OPTARG
            ;;
        # a)
        #     CHECK_ADDRESS=$OPTARG
        #     ;;
        \?)
            usage
            exit 1
            ;;
        *)
            usage
            exit 1
            ;;
        :)
            usage
            exit 1
            ;;
    esac
done
shift "$((OPTIND-1))"

if [ "x" == "x$LOG_FILE_NAME" ]; then
  echo "option -f is required"
  exit ${STATE_WARNING}
fi

# if [ "x" == "x$MULTI_ADDRESS" ]; then
#   echo "option -a is required"
#   exit ${STATE_WARNING}
# fi

LATEST_MED_STATUS=$(tail -${TAIL_LINES} ${LOG_FILE_NAME} | perl -n -e'/(\S+)\/32.*med\s(\d+)\s/ && print "$1 $2\n"' | tail -1)
SERVICE_IP=echo "$LATEST_MED_STATUS" | awk '{print $1}'
MED_VALUE=echo "$LATEST_MED_STATUS" | awk '{print $2}'
COMMUNITY_VALUE=echo "$LATEST_MED_STATUS" | awk '{print $3}'

if [ -z "${SERVICE_IP}"]; then
  echo "No Service IP information found!"
  exit ${STATE_CRITICAL}
fi

if [ -z "${MED_VALUE}"]; then
  echo "No MED information found!"
  exit ${STATE_CRITICAL}
fi

#echo "OK | ${SERVICE_IP}_MED=${MED_VALUE};; ${SERVICE_IP}_CTY=${COMMUNITY_VALUE};;"
echo "OK | ${SERVICE_IP}_MED=${MED_VALUE};;"
exit ${STATE_OK}
