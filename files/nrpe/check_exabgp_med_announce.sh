#!/bin/bash
#
# Check with which Multi-Exit Discriminator value Service IPs are announced
# from ExaBGP, based on systemd service journal.

set -e

STATE_OK=0
STATE_WARNING=1
STATE_CRITICAL=2
STATE_UNKNOWN=3

SERVICE_NAME=exabgp.service

usage ()
{
    echo "Usage: $0 [OPTIONS]"
    echo " -h               Get help"
    echo " -s               systemctl service (defaults to exabgp.service)"
}

while getopts 'hs:' OPTION
do
    case $OPTION in
        h)
            usage
            exit ${STATE_WARNING}
            ;;
        s)
            SERVICE_NAME=${OPTARG}
            ;;
        \?)
            usage
            exit ${STATE_WARNING}
            ;;
        *)
            usage
            exit ${STATE_WARNING}
            ;;
    esac
done
shift "$((OPTIND-1))"

RETURN_METRICS=""
MED_STATUSES_RAW=$(sudo journalctl -e -n10 --unit ${SERVICE_NAME} | awk '/.*announce route/{print $15" "$17 }'|sort -u)
if [ -z "${MED_STATUSES_RAW// }" ]; then
  echo "Did not get any data when trying to read ${LOG_FILE_NAME}."
  exit ${STATE_CRITICAL}
fi

while read -r line; do
  SERVICE_IP=$(echo "$line"|awk '{print $1}')
  MED_VALUE=$(echo "$line"|awk '{print $2}')
  if [ -z "${SERVICE_IP}" ]; then
    echo "No Service IP information found!"
    exit ${STATE_CRITICAL}
  fi
  if [ -z "${MED_VALUE}" ]; then
    echo "No MED information found!"
    exit ${STATE_WARNING}
  fi
  SERVICE_IP_NODOTS="$(echo ${SERVICE_IP}|sed 's/\./_/g')"
  RETURN_METRICS+="${SERVICE_IP_NODOTS}_MED=${MED_VALUE} "
done <<< "$MED_STATUSES_RAW"

if [ -z "${RETURN_METRICS}" ]; then
  echo "No metrics parsed from ${LOG_FILE_NAME}."
  exit ${STATE_CRITICAL}
fi

echo "OK | ${RETURN_METRICS}"
exit ${STATE_OK}
