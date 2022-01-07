#!/usr/bin/python

import argparse
import datetime
import os.path
import sys

NAGIOS_STATE_OK             = 0
NAGIOS_STATE_WARNING        = 1
NAGIOS_STATE_CRITICAL       = 2


def check_date_is_today(status_msg):
    # get the date from the status_msg
    status_msg_datestring = status_msg.split()[0]
    status_msg_date = datetime.datetime.strptime(status_msg_datestring, '%Y-%m-%d').date()
    if status_msg_date == datetime.date.today():
        return True
    else:
        return False

def main():
    parser = argparse.ArgumentParser(description='Check the log file of the key generation process')
    parser.add_argument('-l', '--log-file', dest='log_file', help='Path to the log file')
    args = parser.parse_args()
    # does the log file exist?
    if os.path.exists(args.log_file) == False:
        print("CRITICAL - File " + args.log_file + " does not exist")
        sys.exit(NAGIOS_STATE_CRITICAL)
    # is the file empty?
    if os.path.getsize(args.log_file) == 0:
        print("CRITICAL - File " + args.log_file + " is empty")
        sys.exit(NAGIOS_STATE_CRITICAL)
    # file exists and is not empty
    with open(args.log_file, "r") as log_file:
        # take the last line
        for line in log_file:
          pass
        # line contains the last line of the log file
        status_msg = line
        # does the date on the last line correspond to today?
        if check_date_is_today(status_msg) == False:
            print("CRITICAL - The date of the latest logged message does not match today's date")
            sys.exit(NAGIOS_STATE_CRITICAL)
        print(status_msg)
        if "OK" in status_msg:
            sys.exit(NAGIOS_STATE_OK)
        elif "WARNING" in status_msg:
            sys.exit(NAGIOS_STATE_WARNING)
        # in all other cases, return critical state
        sys.exit(NAGIOS_STATE_CRITICAL)

if __name__ == "__main__":
    main()
