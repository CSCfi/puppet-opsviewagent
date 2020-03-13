#!/bin/bash
#
# Keystone API monitoring script for Sensu/Nagios
#
# Copyright © 2013 eNovance <licensing@enovance.com>
#
# Author: Emilien Macchi <emilien.macchi@enovance.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Requirement: curl
# Updated Darren Glynn 2017-11-27
#

# #RED
set -e

STATE_OK=0
STATE_WARNING=1
STATE_CRITICAL=2
STATE_UNKNOWN=3

usage ()
{
    echo "Usage: $0 [OPTIONS]"
    echo " -h               Get help"
    echo " -H <Auth URL>    URL for obtaining an auth token"
    echo " -U <username>    Username to use to get an auth token"
    echo " -P <password>    Password to use to get an auth token"
    echo " -D <domain>      Domain to use to get an auth token"
}

while getopts 'h:H:U:T:P:' OPTION
do
    case $OPTION in
        h)
            usage
            exit 0
            ;;
        H)
            export OS_AUTH_URL=$OPTARG
            ;;
        U)
            export OS_USERNAME=$OPTARG
            ;;
        P)
            export OS_PASSWORD=$OPTARG
            ;;
        D)
            export OS_USER_DOMAIN=$OPTARG
            ;;
        *)
            usage
            exit 1
            ;;
    esac
done

if ! which curl >/dev/null 2>&1
then
    echo "curl is not installed."
    exit $STATE_UNKNOWN
fi

START=$(date +%s%3N)
TOKEN=$(curl -i -H "Content-Type: application/json" -d '{ "auth": {"identity": {"methods": ["password"],"password": {"user": {"name": "'$OS_USERNAME'","domain": { "name": "'$OS_USER_DOMAIN'"},"password": "'$OS_PASSWORD'" }}}}}' "${OS_AUTH_URL}"/auth/tokens 2>&1 | grep token|awk '{print $5}'|grep -o '".*"' | sed -n 's/.*"\([^"]*\)".*/\1/p')

END=$(date +%s%3N)

TIME=$((END-START))

if [ -z "$TOKEN" ]; then
    echo "Unable to get a token, Keystone API is not responding"
    exit $STATE_CRITICAL
else
    if [ $TIME -gt 10000 ]; then
        echo "Got a token after $TIME milliseconds, Keystone API is taking too long.|token_issue_time_ms=$TIME"
        exit $STATE_WARNING
    else
        echo "Got a token after $TIME milliseconds, Keystone API is working normally.|token_issue_time_ms=$TIME"
        exit $STATE_OK
    fi
fi
