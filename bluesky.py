#!/usr/bin/env python3
import argparse
import subprocess
import json
import sys
from pathlib import Path

def run_curl(method, url, headers=None, data=None):
    cmd = ["curl", "-sS", "-X", method, url, "-H", "Content-Type: application/json"]
    if headers:
        for k, v in headers.items():
            cmd += ["-H", f"{k}: {v}"]
    if data is not None:
        cmd += ["-d", json.dumps(data)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"curl failed: {res.stderr.strip()}")
    # Bluesky errors come back as JSON too; try to decode
    try:
        out = json.loads(res.stdout) if res.stdout else {}
    except json.JSONDecodeError:
        raise RuntimeError(f"Non-JSON response from {url}: {res.stdout[:300]}")
    # Surface error messages if present
    if isinstance(out, dict) and "error" in out:
        raise RuntimeError(f"{method} {url} -> {out.get('error')}: {out.get('message')}")
    return out

def read_creds(path: Path):
    text = path.read_text(encoding="utf-8").strip().splitlines()
    if len(text) < 2:
        raise ValueError("Creds file must have two lines: <handle> on line 1, <app_password> on line 2")
    handle = text[0].strip()
    password = text[1].strip()
    if not handle or not password:
        raise ValueError("Handle or password is empty in creds file")
    return handle, password

def read_keywords(path: Path):
    kws = []
    for line in path.read_text(encoding="utf-8").splitlines():
        kw = line.strip()
        if kw:
            kws.append(kw.lower())
    return kws

def get_session(service, identifier, password):
    url = f"{service}/xrpc/com.atproto.server.createSession"
    payload = {"identifier": identifier, "password": password}
    out = run_curl("POST", url, data=payload)
    access = out.get("accessJwt")
    did = out.get("did") or out.get("didDoc", {}).get("id")
    handle = out.get("handle") or identifier
    if not access or not did:
        raise RuntimeError("Login succeeded but did not return accessJwt and/or did")
    return access, did, handle

def get_all_follows(service, access_jwt, actor_handle, total_limit=100, page_size=100, max_pages=100):
    """
    Fetch up to `total_limit` follows, paging in chunks of `page_size`.
    Adds multiple safety breaks to avoid infinite loops.
    """
    base_url = f"{service}/xrpc/app.bsky.graph.getFollows"
    headers = {"Authorization": f"Bearer {access_jwt}"}

    follows = []
    seen = set()  # de-dupe by DID/handle just in case
    cursor = None
    pages = 0
    fetched = 0

    while fetched < total_limit and pages < max_pages:
        limit = min(page_size, total_limit - fetched)
        q = f"?actor={actor_handle}&limit={limit}"
        if cursor:
            q += f"&cursor={cursor}"

        out = run_curl("GET", base_url + q, headers=headers)

        batch = out.get("follows", []) or []
        new_cursor = out.get("cursor")

        # Stop if the server gives us nothing new
        if not batch:
            break

        # Append up to the remaining quota, de-duping
        for item in batch:
            key = item.get("did") or item.get("handle")
            if key in seen:
                continue
            follows.append(item)
            seen.add(key)
            fetched += 1
            if fetched >= total_limit:
                break

        pages += 1

        # Break if no cursor or a repeating cursor (defensive)
        if not new_cursor or new_cursor == cursor:
            break

        cursor = new_cursor

    return follows

def delete_follow_record(service, access_jwt, my_repo, at_uri):
    """
    at_uri looks like: at://did:plc:ME/app.bsky.graph.follow/3laj123abc
    We need the rkey (last path segment) and collection (app.bsky.graph.follow).
    """
    if not at_uri.startswith("at://"):
        raise ValueError(f"Unexpected follow URI: {at_uri}")
    parts = at_uri.split("/")
    if len(parts) < 5:
        raise ValueError(f"Malformed follow URI: {at_uri}")
    collection = f"{parts[3]}"
    rkey = parts[4]
    url = f"{service}/xrpc/com.atproto.repo.deleteRecord"
    headers = {"Authorization": f"Bearer {access_jwt}"}
    payload = {
        "repo": my_repo,                 # your DID or handle
        "collection": collection,        # "app.bsky.graph.follow"
        "rkey": rkey
    }
    out = run_curl("POST", url, headers=headers, data=payload)
    return out

def main():
    ap = argparse.ArgumentParser(description="Audit who you follow on Bluesky by keywords in bio/description.")
    ap.add_argument("--creds", required=True, help="Path to file: line1=<handle>, line2=<app_password>")
    ap.add_argument("--keywords", required=True, help="Path to newline-separated keywords to keep (case-insensitive)")
    ap.add_argument("--service", default="https://bsky.social", help="PDS base URL (default: https://bsky.social)")
    ap.add_argument("--limit", type=int, default=100, help="Page size for getFollows (max ~100)")
    ap.add_argument("--dry-run", action="store_true", help="Don’t actually unfollow; just show what would happen")
    ap.add_argument("--nodesc", action="store_true",
                    help="Automatically unfollow accounts with an empty bio/description (no prompt; combine with --dry-run to preview)")
    args = ap.parse_args()

    handle, app_password = read_creds(Path(args.creds))
    keywords = read_keywords(Path(args.keywords))
    if not keywords:
        print("No keywords provided; every account will be considered 'no match'.", file=sys.stderr)

    print(f"Logging in as {handle} @ {args.service} ...")
    access, did, confirmed_handle = get_session(args.service, handle, app_password)
    print(f"OK. DID: {did}  Handle: {confirmed_handle}")

    print("Fetching follows ...")
    follows = get_all_follows(args.service, access, confirmed_handle, args.limit)
    print(f"Found {len(follows)} accounts you follow.\n")

    # Iterate and filter by keywords in bio + description
    kept, candidates, empties = 0, 0, 0
    for f in follows:
        actor = f.get("handle") or f.get("did") or "<unknown>"
        display = f.get("displayName") or actor

        # Gather both "bio" and "description" if present
        # - Primary description field (often the user profile bio)
        desc = (f.get("description") or "").strip()
        # - Some payloads (or future shapes) may expose a separate "bio" or nested profile description
        bio = (f.get("bio") or ((f.get("profile") or {}).get("description") or "")).strip()

        # Combined text for keyword matching and display
        text = " ".join([s for s in (bio, desc) if s])
        text_lc = text.lower()

        # Auto-remove accounts with no bio AND no description
        if args.nodesc and not text:
            follow_uri = (f.get("viewer") or {}).get("following")
            print("=" * 72)
            print(f"{display}  (@{actor})")
            print("Bio/Description: (no description)")
            if not follow_uri:
                print("Warning: No follow record URI available (cannot auto-unfollow from here).")
            else:
                if args.dry_run:
                    print(f"[dry-run] Would unfollow (empty description) via record {follow_uri}")
                else:
                    try:
                        delete_follow_record(args.service, access, did, follow_uri)
                        print("Unfollowed (empty description).")
                    except Exception as e:
                        print(f"Failed to unfollow: {e}")
            empties += 1
            continue  # skip keyword checks & prompts

        # Keyword match across both bio + description
        match = any(kw in text_lc for kw in keywords) if keywords else False

        if match:
            kept += 1
            continue  # keep silently

        candidates += 1
        print("=" * 72)
        print(f"{display}  (@{actor})")
        print(f"Bio/Description: {text if text else '(no description)'}")
        print("No keyword match.")
        # Need the follow record URI to unfollow via deleteRecord
        follow_uri = (f.get("viewer") or {}).get("following")
        if not follow_uri:
            print("Warning: No follow record URI available (cannot auto-unfollow from here).")
            print("Skip [n]: ", end="", flush=True)
            choice = sys.stdin.readline().strip().lower()
            continue

        # Prompt the user
        print("Unfollow this account? [y/N]: ", end="", flush=True)
        choice = sys.stdin.readline().strip().lower()
        if choice == "y":
            if args.dry_run:
                print(f"[dry-run] Would unfollow via record {follow_uri}")
            else:
                try:
                    delete_follow_record(args.service, access, did, follow_uri)
                    print("Unfollowed.")
                except Exception as e:
                    print(f"Failed to unfollow: {e}")
        else:
            print("Left untouched.")

    print("\nDone.")
    print(f"Kept (keyword matched): {kept}")
    print(f"Reviewed without match: {candidates}")
    if args.nodesc:
        print(f"Removed (empty description): {empties}")
    if args.dry_run:
        print("NOTE: dry-run mode; no changes were made.")

if __name__ == "__main__":
    main()
