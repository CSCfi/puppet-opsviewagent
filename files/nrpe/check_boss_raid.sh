#!/bin/bash

# Path to the binary
MNV_CLI="/usr/sbin/mnv_cli"

# Execute command and capture output
# 2>&1 redirects stderr to stdout to catch all output
OUTPUT=$($MNV_CLI info -o vd 2>&1)
EXIT_CODE=$?

# Check if the command itself failed
if [ $EXIT_CODE -ne 0 ]; then
  echo "UNKNOWN - Error executing mnv_cli: Exit code $EXIT_CODE | $OUTPUT"
  exit 3
fi

# Extract specific values using grep and awk
RAID_VAL=$(echo "$OUTPUT" | grep "RAID Mode:" | awk '{print $NF}')
PDS_LIST=$(echo "$OUTPUT" | grep "PDs:" | cut -d':' -f2 | xargs)
VD_NUM=$(echo "$OUTPUT" | grep "Total # of VD:" | awk '{print $NF}')

# Logic to determine health
if echo "$OUTPUT" | grep -Ei "Optimal|Functional|Healthy" >/dev/null; then
  echo "OK - RAID Status is Functional"
  echo "Detected Mode: $RAID_VAL"
  echo "PD list: $PDS_LIST"
  echo "Number of VD: $VD_NUM"
  exit 0
elif echo "$OUTPUT" | grep -iq "Degraded"; then
  echo "WARNING - RAID is Degraded | $(echo "$OUTPUT" | tr '\n' ' ')"
  exit 1
else
  echo "CRITICAL - RAID Failure or Unknown Status | $(echo "$OUTPUT" | tr '\n' ' ')"
  exit 2
fi
