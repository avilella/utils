#!/usr/bin/env python3
import argparse
import subprocess
import json
import sys
from pathlib import Path
from datetime import datetime

# ------------------------- HTTP helper -------------------------
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
    try:
        out = json.loads(res.stdout) if res.stdout else {}
    except json.JSONDecodeError:
        raise RuntimeError(f"Non-JSON response from {url}: {res.stdout[:300]}")
    if isinstance(out, dict) and "error" in out:
        raise RuntimeError(f"{method} {url} -> {out.get('error')}: {out.get('message')}")
    return out

# ------------------------- IO helpers -------------------------
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

# ------------------------- ATProto helpers -------------------------
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
    Fetch up to `total_limit` follows (who actor_handle is following).
    """
    base_url = f"{service}/xrpc/app.bsky.graph.getFollows"
    headers = {"Authorization": f"Bearer {access_jwt}"}
    follows, seen = [], set()
    cursor = None
    pages, fetched = 0, 0

    while fetched < total_limit and pages < max_pages:
        limit = min(page_size, total_limit - fetched)
        q = f"?actor={actor_handle}&limit={limit}"
        if cursor: q += f"&cursor={cursor}"
        out = run_curl("GET", base_url + q, headers=headers)
        batch = out.get("follows", []) or []
        new_cursor = out.get("cursor")
        if not batch: break
        for item in batch:
            key = item.get("did") or item.get("handle")
            if key in seen: continue
            follows.append(item); seen.add(key)
            fetched += 1
            if fetched >= total_limit: break
        pages += 1
        if not new_cursor or new_cursor == cursor: break
        cursor = new_cursor
    return follows

def get_followers(service, access_jwt, actor, total_limit=100, page_size=100, max_pages=100):
    """
    Fetch up to `total_limit` followers (who follows actor).
    `actor` can be handle or did.
    """
    base_url = f"{service}/xrpc/app.bsky.graph.getFollowers"
    headers = {"Authorization": f"Bearer {access_jwt}"}
    followers, seen = [], set()
    cursor = None
    pages, fetched = 0, 0

    while fetched < total_limit and pages < max_pages:
        limit = min(page_size, total_limit - fetched)
        q = f"?actor={actor}&limit={limit}"
        if cursor: q += f"&cursor={cursor}"
        out = run_curl("GET", base_url + q, headers=headers)
        batch = out.get("followers", []) or []
        new_cursor = out.get("cursor")
        if not batch: break
        for item in batch:
            key = item.get("did") or item.get("handle")
            if key in seen: continue
            followers.append(item); seen.add(key)
            fetched += 1
            if fetched >= total_limit: break
        pages += 1
        if not new_cursor or new_cursor == cursor: break
        cursor = new_cursor
    return followers

def delete_follow_record(service, access_jwt, my_repo, at_uri):
    """
    Delete a follow record: at://<repo>/app.bsky.graph.follow/<rkey>
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
    payload = {"repo": my_repo, "collection": collection, "rkey": rkey}
    return run_curl("POST", url, headers=headers, data=payload)

def create_follow_record(service, access_jwt, my_repo, subject_did):
    """
    Create a follow record of subject_did in my_repo.
    """
    url = f"{service}/xrpc/com.atproto.repo.createRecord"
    headers = {"Authorization": f"Bearer {access_jwt}"}
    record = {
        "subject": subject_did,
        "createdAt": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    payload = {
        "repo": my_repo,
        "collection": "app.bsky.graph.follow",
        "record": record,
    }
    return run_curl("POST", url, headers=headers, data=payload)

def search_actors_by_keyword(service, access_jwt, keyword, page_limit=50, max_pages=5):
    """
    Search actors by keyword. Returns a list of actor dicts.
    """
    base_url = f"{service}/xrpc/app.bsky.actor.searchActors"
    headers = {"Authorization": f"Bearer {access_jwt}"}
    actors, seen, cursor = [], set(), None
    pages = 0
    while pages < max_pages:
        q = f"?q={keyword}&limit={page_limit}"
        if cursor: q += f"&cursor={cursor}"
        out = run_curl("GET", base_url + q, headers=headers)
        batch = out.get("actors", []) or []
        if not batch: break
        for a in batch:
            key = a.get("did") or a.get("handle")
            if not key or key in seen: continue
            actors.append(a); seen.add(key)
        cursor = out.get("cursor")
        if not cursor: break
        pages += 1
    return actors

# ------------------------- helpers -------------------------
def combine_bio_desc(obj):
    desc = (obj.get("description") or "").strip()
    bio = (obj.get("bio") or ((obj.get("profile") or {}).get("description") or "")).strip()
    return (" ".join([s for s in (bio, desc) if s])).strip()

# ------------------------- Modes -------------------------
def mode_following(args, service, access, did, handle, keywords):
    print("Fetching follows ...")
    follows = get_all_follows(service, access, handle, total_limit=args.limit)
    print(f"Found {len(follows)} accounts you follow.\n")

    # Reorder: empties first if --nodesc
    if args.nodesc:
        follows.sort(key=lambda f: 0 if not combine_bio_desc(f) else 1)

    kept, candidates, empties = 0, 0, 0
    for f in follows:
        text = combine_bio_desc(f)
        actor = f.get("handle") or f.get("did") or "<unknown>"
        display = f.get("displayName") or actor

        # Auto-remove empty if requested
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
                        delete_follow_record(service, access, did, follow_uri)
                        print("Unfollowed (empty description).")
                    except Exception as e:
                        print(f"Failed to unfollow: {e}")
            empties += 1
            continue

        # Keyword match across bio+desc
        match = any(kw in text.lower() for kw in keywords) if keywords else False
        if match:
            kept += 1
            continue

        candidates += 1
        print("=" * 72)
        print(f"{display}  (@{actor})")
        print(f"Bio/Description: {text if text else '(no description)'}")
        print("No keyword match.")
        follow_uri = (f.get("viewer") or {}).get("following")
        if not follow_uri:
            print("Warning: No follow record URI available (cannot auto-unfollow from here).")
            print("Skip [n]: ", end="", flush=True)
            _ = sys.stdin.readline()
            continue

        print("Unfollow this account? [y/N]: ", end="", flush=True)
        choice = sys.stdin.readline().strip().lower()
        if choice == "y":
            if args.dry_run:
                print(f"[dry-run] Would unfollow via record {follow_uri}")
            else:
                try:
                    delete_follow_record(service, access, did, follow_uri)
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

def mode_searching(args, service, access, did, handle, keywords):
    # Build a set of already-followed DIDs to ensure we propose only non-followed
    my_follows = get_all_follows(service, access, handle, total_limit=10000)  # up to 10k
    already = set([ (x.get("did") or x.get("handle")) for x in my_follows if (x.get("did") or x.get("handle")) ])

    print(f"Searching for users by {len(keywords)} keyword(s) ...")
    # Collect candidates across keywords
    candidates_map = {}
    for kw in keywords:
        actors = search_actors_by_keyword(service, access, kw, page_limit=min(50, args.limit), max_pages=max(1, args.limit//50))
        for a in actors:
            key = a.get("did") or a.get("handle")
            if not key or key in already:
                continue
            text = combine_bio_desc(a)
            # Ensure the keyword appears in bio/description specifically
            if kw not in (text.lower() if text else ""):
                continue
            # Also skip if viewer.following says true (server-side)
            if (a.get("viewer") or {}).get("following"):
                continue
            prev = candidates_map.get(key)
            if (not prev) or (len(text) > len(prev["text"])):
                candidates_map[key] = {"actor": a, "text": text, "kw": kw}

    candidates = list(candidates_map.values())
    print(f"Found {len(candidates)} candidate accounts not currently followed.\n")

    added, skipped = 0, 0
    for ent in candidates:
        a = ent["actor"]
        text = ent["text"]
        display = a.get("displayName") or a.get("handle") or a.get("did") or "<unknown>"
        handle_or_did = a.get("handle") or a.get("did") or "<unknown>"

        print("=" * 72)
        print(f"{display}  (@{handle_or_did})")
        print(f"Bio/Description: {text if text else '(no description)'}")
        print(f"Matched keyword: {ent['kw']}")
        print("Follow this account? [y/N]: ", end="", flush=True)
        choice = sys.stdin.readline().strip().lower()
        if choice == "y":
            if args.dry_run:
                print("[dry-run] Would follow (create record).")
                added += 1
            else:
                try:
                    subject_did = a.get("did")
                    if not subject_did:
                        print("No DID for actor; cannot follow.")
                        skipped += 1
                        continue
                    create_follow_record(service, access, did, subject_did)
                    print("Followed.")
                    added += 1
                except Exception as e:
                    print(f"Failed to follow: {e}")
                    skipped += 1
        else:
            skipped += 1
            print("Skipped.")

    print("\nDone.")
    print(f"Followed new accounts: {added}")
    print(f"Skipped: {skipped}")
    if args.dry_run:
        print("NOTE: dry-run mode; no changes were made.")

def mode_degreesearch(args, service, access, did, handle, keywords):
    """
    Depth-based exploration:
      - Seeds: up to --limit of *my follows* (degree 0).
      - For each seed that matches any keyword (bio/description):
          fetch up to --limit of its followers (degree + 1).
          For each follower that matches, prompt to follow.
          If accepted, enqueue that account as a new seed with depth+1.
      - Continue breadth-first until the queue is exhausted or we reach
        the maximum DEPTH (--degreelimit). The number of accepted follows
        does NOT stop the exploration; it only affects breadth of enqueued seeds.
    """
    from collections import deque

    def combine_bio_desc(obj):
        desc = (obj.get("description") or "").strip()
        bio = (obj.get("bio") or ((obj.get("profile") or {}).get("description") or "")).strip()
        return (" ".join([s for s in (bio, desc) if s])).strip()

    def text_matches(obj):
        txt = combine_bio_desc(obj)
        return txt, (txt and any(kw in txt.lower() for kw in keywords))

    # Normalize degreelimit to a minimum of 1 (seed -> followers)
    max_depth = max(1, int(args.degreelimit))

    # Load up to --limit of my current follows (degree 0 seeds)
    base_seeds = get_all_follows(service, access, handle, total_limit=max(1, args.limit))
    print(f"Loaded {len(base_seeds)} of your follows (seed candidates, capped by --limit={args.limit}).")
    print(f"Exploring up to depth (--degreelimit) = {max_depth}.")

    # Build set of accounts I'm already following (by did/handle) to avoid re-suggesting
    already_following = set()
    for s in get_all_follows(service, access, handle, total_limit=10000):
        key = s.get("did") or s.get("handle")
        if key:
            already_following.add(key)

    # Queue of (actor_obj, depth). Start with seeds at depth 0.
    queue = deque((seed, 0) for seed in base_seeds)
    visited_seeds = set()       # which actors we've expanded as seeds
    seen_candidates = set()     # suggestions we've already shown
    added = 0
    skipped = 0

    def key_of(obj):
        return obj.get("did") or obj.get("handle")

    while queue:
        seed, depth = queue.popleft()
        seed_key = key_of(seed)
        if not seed_key or seed_key in visited_seeds:
            continue
        visited_seeds.add(seed_key)

        # Only expand seeds that match keywords
        seed_text, seed_ok = text_matches(seed)
        if not seed_ok:
            continue

        seed_handle_or_did = seed.get("handle") or seed.get("did") or "<unknown>"
        print("=" * 72)
        print(f"Depth {depth} seed: {seed.get('displayName') or seed_handle_or_did} (@{seed_handle_or_did})")
        print(f"Bio/Description: {seed_text if seed_text else '(no description)'}")

        # If we've reached max depth, do not expand further
        if depth >= max_depth:
            print(f"(Reached max depth for this branch; not expanding followers.)")
            continue

        # Fetch followers of this seed (next depth level)
        followers = get_followers(
            service, access, seed_handle_or_did,
            total_limit=max(1, args.limit),
            page_size=min(50, max(1, args.limit)),
            max_pages=max(1, (max(1, args.limit) + 49)//50)
        )
        print(f"  Found {len(followers)} followers to review at depth {depth+1} (capped by --limit={args.limit}).")

        for f in followers:
            f_key = key_of(f)
            if not f_key or f_key in already_following:
                continue

            f_text, f_ok = text_matches(f)
            if not f_ok:
                continue

            # Avoid showing the same candidate multiple times from different seeds
            if f_key in seen_candidates:
                continue
            seen_candidates.add(f_key)

            display = f.get("displayName") or f.get("handle") or f.get("did") or "<unknown>"
            handle_or_did = f.get("handle") or f.get("did") or "<unknown>"
            print("-" * 72)
            print(f"Candidate (depth {depth+1}): {display}  (@{handle_or_did})  — follower of seed above")
            print(f"Bio/Description: {f_text if f_text else '(no description)'}")
            print("Follow this account? [y/N]: ", end="", flush=True)
            choice = sys.stdin.readline().strip().lower()

            if choice == "y":
                # Treat as followed (even in dry-run) to allow further expansion
                already_following.add(f_key)
                if args.dry_run:
                    print("[dry-run] Would follow (create record).")
                    added += 1
                    # Enqueue as a new seed to expand further if within depth budget
                    if depth + 1 <= max_depth - 1:
                        queue.append((f, depth + 1))
                else:
                    try:
                        subject_did = f.get("did")
                        if not subject_did:
                            print("No DID for actor; cannot follow.")
                            skipped += 1
                            continue
                        create_follow_record(service, access, did, subject_did)
                        print("Followed.")
                        added += 1
                        if depth + 1 <= max_depth - 1:
                            queue.append((f, depth + 1))
                    except Exception as e:
                        print(f"Failed to follow: {e}")
                        skipped += 1
            else:
                skipped += 1
                print("Skipped.")

    print("\nDone.")
    print(f"New follows added this session: {added}")
    print(f"Skipped: {skipped}")
    if args.dry_run:
        print("NOTE: dry-run mode; no changes were made.")

# ------------------------- main -------------------------
def main():
    ap = argparse.ArgumentParser(description="Audit / discover follows on Bluesky using keywords in bio/description.")
    ap.add_argument("-m", "--mode", choices=["following","searching","degreesearch"], default="following",
                    help="Mode: 'following' (review current follows), 'searching' (discover by keyword), 'degreesearch' (followers of your keyword-matching follows).")
    ap.add_argument("--creds", required=True, help="Path to file: line1=<handle>, line2=<app_password>")
    ap.add_argument("--keywords", required=True, help="Path to newline-separated keywords (case-insensitive)")
    ap.add_argument("--service", default="https://bsky.social", help="PDS base URL (default: https://bsky.social)")
    ap.add_argument("--limit", type=int, default=100, help="For following/searching: page-size/limit used in those modes.")
    ap.add_argument("--degreelimit", type=int, default=100,
                    help="For degreesearch: maximum DEPTH (levels) to explore from your seeds (min 1).")
    ap.add_argument("--dry-run", action="store_true", help="Don’t actually change follows; just show what would happen")
    ap.add_argument("--nodesc", action="store_true",
                    help="(following mode only) Auto-unfollow accounts with empty bio/description first (no prompt; combine with --dry-run).")
    args = ap.parse_args()

    handle, app_password = read_creds(Path(args.creds))
    keywords = read_keywords(Path(args.keywords))
    if not keywords:
        print("No keywords provided; nothing to match.", file=sys.stderr)

    print(f"Logging in as {handle} @ {args.service} ...")
    access, did, confirmed_handle = get_session(args.service, handle, app_password)
    print(f"OK. DID: {did}  Handle: {confirmed_handle}")

    if args.mode == "following":
        mode_following(args, args.service, access, did, confirmed_handle, keywords)
    elif args.mode == "searching":
        mode_searching(args, args.service, access, did, confirmed_handle, keywords)
    else:
        mode_degreesearch(args, args.service, access, did, confirmed_handle, keywords)

if __name__ == "__main__":
    main()
