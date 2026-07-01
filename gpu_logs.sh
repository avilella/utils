#!/bin/bash

# Print the table header (Changed "MEMORY" to "VRAM")
printf "%-25s | %-8s | %-15s | %-12s | %-15s\n" "GPU" "PID" "PROCESS" "VRAM" "ELAPSED TIME"
printf "%s\n" "------------------------------------------------------------------------------------"

# Query nvidia-smi (used_memory is the VRAM used by the PID)
nvidia-smi --query-compute-apps=gpu_name,pid,process_name,used_memory --format=csv,noheader | while IFS=, read -r gpu pid name mem; do
    # Strip whitespace from PID
    pid=$(echo $pid | tr -d ' ')
    
    # Get elapsed time from ps, suppressing errors
    etime=$(ps -p "$pid" -o etime= 2>/dev/null | tr -d ' ')
    
    # Fallback if time isn't found
    if [ -z "$etime" ]; then
        etime="N/A"
    fi
    
    # Clean up whitespace for formatting
    gpu=$(echo $gpu | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
    name=$(echo $name | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
    mem=$(echo $mem | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')

    # Print the formatted row
    printf "%-25s | %-8s | %-15s | %-12s | %-15s\n" "$gpu" "$pid" "$name" "$mem" "$etime"
done
