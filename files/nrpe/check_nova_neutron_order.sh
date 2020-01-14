#!/bin/bash
#
# Rudimentary check for monitoring that neutron rules are at the very top
# of iptables ordering.

set -e

STATE_OK=0
STATE_WARNING=1
STATE_CRITICAL=2
STATE_UNKNOWN=3

usage ()
{
    echo "Usage: $0 [OPTIONS]"
    echo " -h               Get help"
}

while getopts 'h:' OPTION
do
    case $OPTION in
        h)
            usage
            exit ${STATE_WARNING}
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

IPTABLES_NEUTRON_STATUS="$(/var/log/nrpe/iptables --list --numeric|grep -E '^nova-filter-top|^neutron-filter-top'|head -1|grep neutron)"
RETURNCODE=$?

if [ "${RETURNCODE}" -ne 0 ]; then
  echo "Nonzero $RETURNCODE returned from iptables ordering check."
  exit ${STATE_CRITICAL}
fi

echo "OK | ${IPTABLES_NEUTRON_STATUS}"
exit ${STATE_OK}
