#!/bin/bash

# 1. Create a mapping of GPU UUID to its Index (0 or 1)
declare -A gpu_idx_map
while IFS=, read -r idx uuid; do
    # Strip whitespace
    uuid=$(echo "$uuid" | tr -d ' ')
    idx=$(echo "$idx" | tr -d ' ')
    gpu_idx_map["$uuid"]=$idx
done < <(nvidia-smi --query-gpu=index,gpu_uuid --format=csv,noheader)

# 2. Print the table header (Expanded width for both time columns)
printf "%-8s | %-8s | %-15s | %-12s | %-25s | %-15s\n" "GPU ID" "PID" "PROCESS" "VRAM" "STARTED (WALLCLOCK)" "ELAPSED"
printf "%s\n" "--------------------------------------------------------------------------------------------------------"

# 3. Query compute apps and map them to the correct GPU ID via UUID
nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_memory --format=csv,noheader | while IFS=, read -r uuid pid name mem; do
    
    # Strip whitespace from identifiers
    uuid=$(echo "$uuid" | tr -d ' ')
    pid=$(echo "$pid" | tr -d ' ')
    
    # Lookup the simple GPU ID
    gpu_id=${gpu_idx_map["$uuid"]}
    
    # Get exact wallclock start time (lstart) and elapsed time (etime) from ps
    wtime=$(ps -p "$pid" -o lstart= 2>/dev/null)
    etime=$(ps -p "$pid" -o etime= 2>/dev/null | tr -d ' ')
    
    # Fallbacks if a process dies mid-query
    if [ -z "$wtime" ]; then wtime="N/A"; fi
    if [ -z "$etime" ]; then etime="N/A"; fi
    
    # Clean up whitespace for formatting
    wtime=$(echo "$wtime" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
    name=$(echo "$name" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
    mem=$(echo "$mem" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')

    # Print the formatted row
    printf "GPU %-4s | %-8s | %-15s | %-12s | %-25s | %-15s\n" "$gpu_id" "$pid" "$name" "$mem" "$wtime" "$etime"
done
