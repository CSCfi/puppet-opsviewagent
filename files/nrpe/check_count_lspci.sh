#!/usr/bin/env bash
#
# Simply cout devices in output of lspci
#
# Usage: check_count_lspci.sh [-d device] [-w warning] [-c critical]
#   -d, --device                What to grep for in lspci
#   -w, --warning WARNING       Warning value (percent)
#   -c, --critical CRITICAL     Critical value (percent)
#   -H, --help                  Display this screen
#
# Written by Johan Guldmyr @ CSC 2018

while [[ -n "$1" ]]; do
  case $1 in
    --device | -d)
      device=$2
      shift
      ;;
    --warning | -w)
      warn=$2
      shift
      ;;
    --critical | -c)
      crit=$2
      shift
      ;;
    --help | -H)
      sed -n '2,11p' "$0" | tr -d '#'
      exit 3
      ;;
    *)
      echo "Unknown argument: $1"
      exec "$0" --help
      exit 3
      ;;
  esac
  shift
done

if [[ $warn -ge $crit ]]; then
  echo "UNKNOWN - warn ($warn) can't be greater than critical ($crit)"
  exit 3
fi
if [[ "x$device" == "x" ]]; then
  echo "UNKNOWN - what to grep for? Specify -d 'NVIDIA' for example."
  exit 3
fi

if ! [ -x "$(command -v lspci)" ]; then
  echo "UNKNOWN - lspci not in path"
  exit 3
fi

output=$(lspci|grep $device|wc -l)

metricname=$(echo $device|tr -cd '[[:alnum:]]._-')
status="$output $device devices found | ${metricname}devices=$output"

if [[ $output -lt $crit ]]; then
  echo "CRITICAL - ${status}"
  exit 2
elif [[ $output -lt $warn ]]; then
  echo "WARNING - ${status}"
  exit 1
else
  echo "OK - ${status}"
  exit 0
fi
