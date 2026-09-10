#!/bin/bash
# Read the JSON payload piped from agy
PAYLOAD=$(cat)

# Optional: Log the payload temporarily to find the exact JSON path if the summary is missing
# echo "$PAYLOAD" >> /tmp/agy_stop_payload.json

TRANSCRIPT_PATH=$(echo "$PAYLOAD" | jq -r '.transcriptPath' 2>/dev/null)

# Extract the last message from the transcript using jq.
if [ -f "$TRANSCRIPT_PATH" ] && command -v jq >/dev/null 2>&1; then
  SUMMARY=$(jq -c 'select(.type == "PLANNER_RESPONSE" and .content != null) | .content' "$TRANSCRIPT_PATH" 2>/dev/null | tail -n 1 | jq -r . 2>/dev/null)
else
  SUMMARY="Task completed (details unavailable)"
fi

if [ -z "$SUMMARY" ]; then
  SUMMARY="Task completed"
fi

# Clean up any potential markdown comments like <!-- GOAL_COMPLETE -->
SUMMARY=$(echo "$SUMMARY" | sed 's/<!--.*-->//g' | sed '/^$/d')

# Trigger your notification tool by piping the text
# This ensures nt's stdin check works correctly and actually reads the message
echo "Antigravity: $SUMMARY" | /home/avilella/bin/nt > /dev/null 2>&1
echo "{}"
exit 0

