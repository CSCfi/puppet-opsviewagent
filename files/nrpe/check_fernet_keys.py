#!/usr/bin/python

import argparse
import os.path
import sys

NAGIOS_STATE_OK             = 0
NAGIOS_STATE_WARNING        = 1
NAGIOS_STATE_CRITICAL       = 2


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
        print(status_msg)
        if status_msg.contains("OK"):
            sys.exit(NAGIOS_STATE_OK)
        elif status_msg.contains("WARNING"):
            sys.exit(NAGIOS_STATE_WARNING)
        # in all other cases, return critical state
        sys.exit(NAGIOS_STATE_CRITICAL)

if __name__ == "__main__":
    main()
