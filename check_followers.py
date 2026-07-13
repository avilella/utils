#!/usr/bin/env python3
import csv
import sys
from pathlib import Path

# This imports all your existing API logic from bluesky.py!
import bluesky

def main():
    if len(sys.argv) != 4:
        print("Usage: python check_followers.py <creds_file> <target_handle> <input.tsv>")
        print("Example: python check_followers.py bluesky.txt albertvilella.bsky.social bioinformatics.outt.tsv")
        sys.exit(1)

    creds_path = sys.argv[1]
    target_handle = sys.argv[2]
    tsv_path = sys.argv[3]

    print(f"Logging in...")
    handle, pwd = bluesky.read_creds(Path(creds_path))
    # We use your existing session generator
    access, did, confirmed_handle = bluesky.get_session("https://bsky.social", handle, pwd)
    print(f"OK. Logged in as {confirmed_handle}")

    # 1. Read the exported TSV file to get the list of DIDs
    exported_dids = {}
    print(f"\nReading {tsv_path}...")
    try:
        with open(tsv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                # Store the whole row so we can re-export the matches later
                exported_dids[row["DID"]] = row
    except Exception as e:
        print(f"Failed to read TSV: {e}")
        sys.exit(1)

    print(f"Loaded {len(exported_dids)} accounts from the TSV.")

    # 2. Fetch all followers of the target account
    print(f"\nFetching all followers for {target_handle}... (this may take a bit for large accounts)")
    followers_dids = set()
    pages = 0
    
    # Using your existing follower pagination, with a massive max_pages limit to ensure it exhausts
    try:
        for batch in bluesky.iter_followers("https://bsky.social", access, target_handle, batch_size=100, max_pages=100000):
            pages += 1
            for user in batch:
                followers_dids.add(user.get("did"))
            if pages % 10 == 0:
                sys.stdout.write(f"\rFetched {len(followers_dids)} followers so far...")
                sys.stdout.flush()
    except Exception as e:
        print(f"\nError while fetching followers: {e}")

    print(f"\nFinished! {target_handle} has a total of {len(followers_dids)} followers.")

    # 3. Find the intersection between your TSV and their followers
    intersection = set(exported_dids.keys()).intersection(followers_dids)
    print(f"\nFound {len(intersection)} accounts from your TSV that are following {target_handle}!\n")
    
    # 4. Output the results to a new TSV
    if intersection:
        out_file = f"matches_following_{target_handle}.tsv"
        with open(out_file, "w", encoding="utf-8") as f:
            f.write("DID\tHandle\tDisplayName\tBio\n")
            for match_did in intersection:
                row = exported_dids[match_did]
                f.write(f"{row['DID']}\t{row['Handle']}\t{row['DisplayName']}\t{row['Bio']}\n")
        print(f"Saved the matching accounts to: {out_file}")

if __name__ == "__main__":
    main()
