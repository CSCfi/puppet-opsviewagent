#!/bin/bash
#
# Check that given interface is UP and has given address.

#set -e

STATE_OK=0
STATE_WARNING=1
STATE_CRITICAL=2
STATE_UNKNOWN=3

usage ()
{
    echo "Usage: $0 [OPTIONS]"
    echo " -h               Get help"
    echo " -i <interface>   Interface to inspect"
    echo " -a <address>     Address whose presence to check. Can be repeated."
}

if (($# == 0)); then
  usage
  exit 1
fi

while getopts ':i:a:h' OPTION
do
    case $OPTION in
        h)
            usage
            exit 0
            ;;
        i)
            IF_NAME=$OPTARG
            ;;
        a)
            MULTI_ADDRESS+=("$OPTARG")
            ;;
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

if [ "x" == "x$IF_NAME" ]; then
  echo "option -i is required"
  exit
fi

if [ "x" == "x$MULTI_ADDRESS" ]; then
  echo "option -a is required"
  exit
fi

IF_HAS_UP=$(ip -4 -o link show ${IF_NAME}|grep -Po "<.*,UP,.*>")
if [ $? -ne 0 ]; then
  echo "Interface ${IF_NAME} is not up."
  exit ${STATE_CRITICAL}
else
  echo "Interface ${IF_NAME} is up."
fi

for IF_CHECK_ADDR in "${MULTI_ADDRESS[@]}"; do
  IF_HAS_IP=$(ip -4 -o addr show "${IF_NAME}"|grep -Po "${IF_CHECK_ADDR}")
  if [ $? -ne 0 ]; then
    echo "Address ${IF_CHECK_ADDR} missing from interface ${IF_NAME}."
    exit ${STATE_WARNING}
  else
    echo "Address ${IF_CHECK_ADDR} present on interface ${IF_NAME}."
  fi
done

exit ${STATE_OK}
