#!/bin/bash

# Check if the correct number of arguments is provided
if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <python_script_name> <threshold_in_GB>"
    echo "Example: $0 my_script.py 1.5"
    exit 1
fi

SCRIPT_NAME=$1
THRESHOLD_GB=$2

# Find the PID of the running Python script (takes the first match)
PID=$(pgrep -f "python.*$SCRIPT_NAME" | head -n 1)

if [ -z "$PID" ]; then
    echo "Error: Could not find a running Python process matching '$SCRIPT_NAME'"
    exit 1
fi

echo "Monitoring PID $PID ($SCRIPT_NAME)..."
echo "Will alert if memory exceeds $THRESHOLD_GB GB. Press [Ctrl+C] to stop."
echo "-------------------------------------------------------------------"

# Loop while the process is still running
while kill -0 "$PID" 2>/dev/null; do
    # Get the Resident Set Size (RSS) in KB
    RSS_KB=$(ps -p "$PID" -o rss=)
    
    # Check if we got a valid number (process might have died exactly on this check)
    if [ -n "$RSS_KB" ]; then
        # Use awk for floating point math and comparison
        awk -v rss="$RSS_KB" -v thresh="$THRESHOLD_GB" 'BEGIN {
            # Convert KB to GB (1 GB = 1024 * 1024 KB)
            rss_gb = rss / 1048576;
            
            if (rss_gb > thresh) {
                printf "[$(date +\"%Y-%m-%d %H:%M:%S\")] ALERT: Memory usage at %.2f GB (Threshold: %.2f GB)\n", rss_gb, thresh;
            }
        }'
    fi
    
    # Wait 2 seconds before checking again (adjust as needed)
    sleep 2
done

echo "Process $PID has terminated."
