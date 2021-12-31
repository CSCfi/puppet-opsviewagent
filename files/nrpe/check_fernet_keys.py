#!/usr/bin/python

import argparse
import os.path
import subprocess
import sys

NAGIOS_STATE_OK             = 0
NAGIOS_STATE_WARNING        = 1
NAGIOS_STATE_CRITICAL       = 2


def run_shell_command(command):
    return subprocess.run([command], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, encoding='utf-8').stdout

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
    # take the last line
    status_msg = run_shell_command("tail -n 1 " + args.log_file)
    print(status_msg)
    if status_msg.contains("OK"):
        sys.exit(NAGIOS_STATE_OK)
    elif status_msg.contains("WARNING"):
        sys.exit(NAGIOS_STATE_WARNING)
    # in all other cases, return critical state
    sys.exit(NAGIOS_STATE_CRITICAL)

if __name__ == "__main__":
    main()
