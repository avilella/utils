#!/usr/bin/env python3

import os
import shutil
import argparse
from datetime import datetime, timedelta

def main():
    # Set up argument parsing
    parser = argparse.ArgumentParser(description="Organize files older than a specified number of days into YYYY/MM/DD folders.")
    parser.add_argument(
        '--last-days', 
        type=int, 
        default=30, 
        help="Move files older than this many days (default: 30)"
    )
    args = parser.parse_args()

    # Get current directory and calculate the threshold date
    current_dir = os.getcwd()
    now = datetime.now()
    threshold_date = now - timedelta(days=args.last_days)
    
    script_name = os.path.basename(__file__)
    moved_count = 0

    # Iterate through items in the immediate directory only
    for filename in os.listdir(current_dir):
        file_path = os.path.join(current_dir, filename)

        # Skip directories and the script itself
        if not os.path.isfile(file_path) or filename == script_name:
            continue

        # Retrieve the file's modification timestamp
        mtime = os.path.getmtime(file_path)
        file_date = datetime.fromtimestamp(mtime)

        # Check if the file is older than the threshold
        if file_date < threshold_date:
            # Extract Year, Month, and Day strings
            year_str = file_date.strftime('%Y')
            month_str = file_date.strftime('%m')
            day_str = file_date.strftime('%d')

            # Build the target directory path
            target_dir = os.path.join(current_dir, year_str, month_str, day_str)

            # Create the nested directories if they don't exist
            os.makedirs(target_dir, exist_ok=True)

            # Move the file
            target_path = os.path.join(target_dir, filename)
            
            try:
                shutil.move(file_path, target_path)
                print(f"Moved: '{filename}' -> {year_str}/{month_str}/{day_str}/")
                moved_count += 1
            except Exception as e:
                print(f"Error moving '{filename}': {e}")

    print(f"\nOperation complete. Moved {moved_count} file(s).")

if __name__ == "__main__":
    main()
