#!/usr/bin/env python3
import argparse
import csv
import sys
import time
from pathlib import Path
from urllib.parse import quote

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except ImportError:
    print("Error: scikit-learn is required for text similarity.", file=sys.stderr)
    print("Please install it using: pip install scikit-learn", file=sys.stderr)
    sys.exit(1)

# Import your existing Bluesky API logic
import bluesky

def get_recent_posts(service, access_jwt, actor, limit=20):
    """
    Fetches the most recent posts for an actor.
    Extracts and combines the text from those posts.
    """
    url = f"{service}/xrpc/app.bsky.feed.getAuthorFeed?actor={quote(actor)}&limit={limit}&filter=posts_no_replies"
    headers = {"Authorization": f"Bearer {access_jwt}"}
    try:
        res = bluesky.run_curl("GET", url, headers=headers)
        feed = res.get("feed", [])
        texts = []
        for item in feed:
            post = item.get("post", {})
            record = post.get("record", {})
            text = record.get("text", "")
            if text:
                texts.append(text)
        return " ".join(texts)
    except Exception as e:
        # Silently fail for individual API errors to keep the pipeline moving
        return ""

def get_all_follows(service, access_jwt, actor):
    """
    Fetches all accounts the given actor is currently following.
    Returns a set of DIDs.
    """
    follows = set()
    cursor = None
    headers = {"Authorization": f"Bearer {access_jwt}"}

    while True:
        url = f"{service}/xrpc/app.bsky.graph.getFollows?actor={quote(actor)}&limit=100"
        if cursor:
            url += f"&cursor={quote(cursor)}"

        try:
            res = bluesky.run_curl("GET", url, headers=headers)
            for follow in res.get("follows", []):
                follows.add(follow.get("did"))
            
            cursor = res.get("cursor")
            if not cursor:
                break
        except Exception as e:
            # Silently fail and break pagination on error
            break
            
    return follows

def main():
    parser = argparse.ArgumentParser(description="Predict likely followers based on post content similarity.")
    parser.add_argument("-i", "--inputfile", required=True, help="TSV file containing candidate accounts to evaluate.")
    parser.add_argument("--followers", required=True, help="TSV file containing your current followers.")
    parser.add_argument("--creds", required=True, help="Path to bluesky credentials file.")
    parser.add_argument("--limit", type=int, default=50, help="Number of top predicted accounts to output (default: 50).")
    parser.add_argument("--tag", default="tool", help="Tag to append to the output filename (default: 'tool').")
    parser.add_argument("--outdir", default=None, help="Output directory. Defaults to the same directory as the input file.")
    parser.add_argument("--verbose", action="store_true", help="Print detailed processing steps to STDERR.")
    parser.add_argument("--refresh", action="store_true", help="Force recalculation. If off, checks if output exists and exits.")
    parser.add_argument("--new-following", action="store_true", help="Filter out accounts the originating account is already following.")

    args = parser.parse_args()

    input_path = Path(args.inputfile)
    if not input_path.is_file():
        print(f"Error: Input file '{input_path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    followers_path = Path(args.followers)
    if not followers_path.is_file():
        print(f"Error: Followers file '{followers_path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    # --- Cache / Refresh Logic ---
    out_dir = Path(args.outdir) if args.outdir else input_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    out_filename = f"{input_path.stem}.{args.tag}.csv"
    out_path = out_dir / out_filename

    if not args.refresh:
        if out_path.exists() and out_path.stat().st_size > 0:
            if args.verbose:
                print(f"[INFO] Found existing, non-empty output file. Skipping recalculation.", file=sys.stderr)
            print(out_path.resolve())
            sys.exit(0)
        else:
            if args.verbose:
                print(f"[INFO] Output file missing or empty. Proceeding...", file=sys.stderr)

    # --- Login ---
    if args.verbose:
        print("[INFO] Logging into Bluesky API...", file=sys.stderr)
    handle, app_password = bluesky.read_creds(Path(args.creds))
    service = "https://bsky.social"
    access, did, confirmed_handle = bluesky.get_session(service, handle, app_password)

    # --- Fetch Current Follows (if flag is set) ---
    current_follows = set()
    if args.new_following:
        if args.verbose:
            print(f"[INFO] Fetching current following list for {confirmed_handle} to filter out existing follows...", file=sys.stderr)
        current_follows = get_all_follows(service, access, did)

    # --- 1. Build Follower Profile ---
    if args.verbose:
        print(f"[INFO] Reading current followers from {followers_path}...", file=sys.stderr)

    follower_texts = []
    with open(followers_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        followers_list = list(reader)

    if args.verbose:
        print(f"[INFO] Fetching recent posts for {len(followers_list)} followers...", file=sys.stderr)

    for idx, row in enumerate(followers_list):
        f_did = row.get("DID")
        if not f_did:
            continue
        text = get_recent_posts(service, access, f_did, limit=20)
        if text:
            follower_texts.append(text)

        if args.verbose and (idx + 1) % 50 == 0:
            print(f"        ... fetched {idx + 1}/{len(followers_list)} followers", file=sys.stderr)

    combined_follower_text = " ".join(follower_texts)

    if not combined_follower_text.strip():
        print("Error: Could not extract any post text from your followers.", file=sys.stderr)
        sys.exit(1)

    # --- 2. Evaluate Candidates ---
    if args.verbose:
        print(f"\n[INFO] Reading candidate accounts from {input_path}...", file=sys.stderr)

    candidates = []
    with open(input_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            candidates.append(row)

    if args.verbose:
        print(f"[INFO] Processing {len(candidates)} candidates...", file=sys.stderr)

    candidate_docs = []
    valid_candidates = []

    for idx, row in enumerate(candidates):
        c_did = row.get("DID")
        if not c_did:
            continue

        # Skip if we already follow this user (and the flag is active)
        if args.new_following and (c_did in current_follows or c_did == did):
            continue

        text = get_recent_posts(service, access, c_did, limit=20)
        # If they haven't posted anything, we skip them or treat them as zero similarity
        if text.strip():
            candidate_docs.append(text)
            valid_candidates.append(row)

        if args.verbose and (idx + 1) % 50 == 0:
            print(f"        ... processed {idx + 1}/{len(candidates)} candidates", file=sys.stderr)

    if not valid_candidates:
        print("Error: Could not extract any post text from the valid candidate accounts.", file=sys.stderr)
        sys.exit(1)

    # --- 3. Calculate Similarity ---
    if args.verbose:
        print("\n[INFO] Vectorizing text and calculating similarity scores...", file=sys.stderr)

    # Document 0 is the massive follower profile. Documents 1 through N are the candidates.
    all_docs = [combined_follower_text] + candidate_docs

    vectorizer = TfidfVectorizer(stop_words='english', max_features=10000)
    tfidf_matrix = vectorizer.fit_transform(all_docs)

    # Calculate cosine similarity between Doc 0 (followers) and all other docs
    follower_vector = tfidf_matrix[0:1]
    candidate_vectors = tfidf_matrix[1:]

    similarities = cosine_similarity(follower_vector, candidate_vectors).flatten()

    # Bind scores to candidates and sort
    scored_candidates = []
    for i, row in enumerate(valid_candidates):
        row["SimilarityScore"] = round(similarities[i], 4)
        scored_candidates.append(row)

    scored_candidates.sort(key=lambda x: x["SimilarityScore"], reverse=True)
    top_candidates = scored_candidates[:args.limit]

    # --- 4. Write Output ---
    if args.verbose:
        print(f"\n[INFO] Writing top {len(top_candidates)} matches to {out_path}...", file=sys.stderr)

    if not top_candidates:
        print("Error: No candidates left to output.", file=sys.stderr)
        sys.exit(1)

    out_fieldnames = list(top_candidates[0].keys())
    # Reorder to put Score right after Handle
    if "SimilarityScore" in out_fieldnames:
        out_fieldnames.remove("SimilarityScore")
        out_fieldnames.insert(2, "SimilarityScore")

    with open(out_path, mode="w", encoding="utf-8", newline="") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=out_fieldnames, delimiter=",")
        writer.writeheader()
        writer.writerows(top_candidates)

    if args.verbose:
        print("[DONE] Prediction complete.", file=sys.stderr)

    # EXACTLY ONE print to standard output
    print(out_path.resolve())

if __name__ == "__main__":
    main()
