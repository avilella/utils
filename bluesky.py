#!/usr/bin/env python3
import argparse
import subprocess
import json
import sys
from pathlib import Path
from datetime import datetime
from collections import deque, Counter
import re

"""
Bluesky follow/unfollow/search tool (batched, v3)

This version adds per-100-account STDERR stats during *degreesearch*,
while keeping the batched streaming structure across modes.

Modes:
  - following     : review/manage the accounts you already follow
  - searching     : discover accounts by keyword search
  - degreesearch  : breadth-first exploration across followers of matching seeds
  - wordmap       : build a word frequency map from bios/descriptions (followers or following)

Key structure:
  * Pagination functions yield batches of size --limit.
  * Actions occur batch-by-batch, not after preloading huge lists.
"""

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
    # Treat each line as a *phrase*; normalize whitespace and lowercase
    # so multi-word entries match as a contiguous phrase (case-insensitive).
    kws = []
    for line in path.read_text(encoding="utf-8").splitlines():
        kw = " ".join(line.strip().lower().split())
        if kw:
            kws.append(kw)
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

# ------------------------- Pagination helpers (generators) -------------------------
def iter_follows(service, access_jwt, actor_handle, batch_size=100, max_pages=1000):
    """
    Yield lists of follows (accounts you follow) in batches of size `batch_size`.
    """
    base_url = f"{service}/xrpc/app.bsky.graph.getFollows"
    headers = {"Authorization": f"Bearer {access_jwt}"}
    cursor = None
    pages = 0
    while pages < max_pages:
        q = f"?actor={actor_handle}&limit={max(1, int(batch_size))}"
        if cursor:
            q += f"&cursor={cursor}"
        out = run_curl("GET", base_url + q, headers=headers)
        batch = out.get("follows", []) or []
        if not batch:
            break
        yield batch
        cursor_new = out.get("cursor")
        pages += 1
        if not cursor_new or cursor_new == cursor:
            break
        cursor = cursor_new

def iter_followers(service, access_jwt, actor, batch_size=100, max_pages=1000):
    """
    Yield the 'followers' list page-by-page (batches of size <= batch_size).
    """
    base_url = f"{service}/xrpc/app.bsky.graph.getFollowers"
    headers = {"Authorization": f"Bearer {access_jwt}"}
    cursor = None
    pages = 0
    while pages < max_pages:
        q = f"?actor={actor}&limit={max(1, int(batch_size))}"
        if cursor:
            q += f"&cursor={cursor}"
        out = run_curl("GET", base_url + q, headers=headers)
        batch = out.get("followers", []) or []
        if not batch:
            break
        yield batch
        cursor_new = out.get("cursor")
        pages += 1
        if not cursor_new or cursor_new == cursor:
            break
        cursor = cursor_new

def iter_search_actors(service, access_jwt, keyword, batch_size=50, max_pages=5):
    """
    Search actors by keyword and yield results in batches (pages).
    """
    base_url = f"{service}/xrpc/app.bsky.actor.searchActors"
    headers = {"Authorization": f"Bearer {access_jwt}"}
    cursor = None
    pages = 0
    while pages < max_pages:
        q = f"?q={keyword}&limit={max(1, int(batch_size))}"
        if cursor:
            q += f"&cursor={cursor}"
        out = run_curl("GET", base_url + q, headers=headers)
        batch = out.get("actors", []) or []
        if not batch:
            break
        yield batch
        cursor = out.get("cursor")
        pages += 1
        if not cursor:
            break

# ------------------------- Record helpers -------------------------
def delete_follow_record(service, access_jwt, my_repo, at_uri):
    """
    Delete a follow record: at://<repo>/app.bsky.graph.follow/<rkey>
    """
    if not at_uri or not at_uri.startswith("at://"):
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

# ------------------------- List helpers -------------------------
def _build_list_name_from_keywords(keywords, max_len=64):
    # Deterministic name: sorted unique keywords joined by '/'.
    # If it exceeds max_len, include as many as fit and append '/+N' for overflow.
    toks = sorted({(kw or '').strip().lower() for kw in (keywords or []) if (kw or '').strip()})
    if not toks:
        return "keywords"
    name = "/".join(toks)
    if len(name) <= max_len:
        return name
    pieces, used = [], 0
    for t in toks:
        sep = "/" if pieces else ""
        if used + len(sep) + len(t) > max_len - 4:  # reserve 4 chars for '/+N'
            break
        pieces.append(t)
        used += len(sep) + len(t)
    more = len(toks) - len(pieces)
    return "/".join(pieces) + f"/+{more}"

def create_list_record(service, access_jwt, my_repo, name, purpose="app.bsky.graph.defs#curatelist", description=None):
    # Create a curated or moderation list in your repo and return {"uri": ..., "cid": ...}.
    url = f"{service}/xrpc/com.atproto.repo.createRecord"
    headers = {"Authorization": f"Bearer {access_jwt}"}
    record = {
        "purpose": purpose,
        "name": name,
        "createdAt": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    if description:
        record["description"] = description
    payload = {
        "repo": my_repo,
        "collection": "app.bsky.graph.list",
        "record": record,
    }
    return run_curl("POST", url, headers=headers, data=payload)

def create_listitem_record(service, access_jwt, my_repo, list_uri, subject_did):
    # Add `subject_did` to a list by creating an app.bsky.graph.listitem record.
    url = f"{service}/xrpc/com.atproto.repo.createRecord"
    headers = {"Authorization": f"Bearer {access_jwt}"}
    record = {
        "subject": subject_did,
        "list": list_uri,  # at://<your-did>/app.bsky.graph.list/<rkey>
        "createdAt": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    payload = {
        "repo": my_repo,
        "collection": "app.bsky.graph.listitem",
        "record": record,
    }

# ------------------------- text helpers -------------------------
def combine_bio_desc(obj):
    desc = (obj.get("description") or "").strip()
    bio = (obj.get("bio") or ((obj.get("profile") or {}).get("description") or "")).strip()
    return (" ".join([s for s in (bio, desc) if s])).strip()

def matches_any_keyword(text, keywords):
    """
    Case-insensitive *phrase* match: each keyword line is a full phrase.
    Normalize whitespace on both sides so 'Computational   Biologist'
    in the keywords file matches 'computational biologist' in bios.
    """
    if not text or not keywords:
        return False
    t = " ".join(text.lower().split())
    return any(kw in t for kw in keywords)

# ------------------------- Modes (batched) -------------------------
def mode_following(args, service, access, did, handle, keywords):
    print("Streaming your follows in batches ...")
    batch_size = max(1, args.limit)
    kept, reviewed_no_match, empties = 0, 0, 0
    batches = 0

    for follows in iter_follows(service, access, handle, batch_size=batch_size, max_pages=10000):
        batches += 1
        print(f"\n--- Batch {batches} (size={len(follows)}) ---")

        if args.nodesc:
            follows.sort(key=lambda f: 0 if not combine_bio_desc(f) else 1)

        for f in follows:
            text = combine_bio_desc(a)
            # Require full-phrase match for the line from --keywords (case-insensitive)
            if not matches_any_keyword(text, [kw]):
                continue

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

            if matches_any_keyword(text, keywords):
                kept += 1
                continue

            reviewed_no_match += 1
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
    print(f"Reviewed without match: {reviewed_no_match}")
    if args.nodesc:
        print(f"Removed (empty description): {empties}")
    if args.dry_run:
        print("NOTE: dry-run mode; no changes were made.")

def mode_searching(args, service, access, did, handle, keywords):
    if not keywords:
        print("No keywords provided; nothing to search.", file=sys.stderr)
        return

    print(f"Searching for users by {len(keywords)} keyword(s) in batches of {args.limit} ...")
    seen = set()
    session_followed = set()
    added, skipped = 0, 0
    batch_size = max(1, args.limit)

    for kw in keywords:
        pages = 0
        for page in iter_search_actors(service, access, kw, batch_size=min(50, batch_size),
                                       max_pages=max(1, (batch_size + 49)//50)):
            pages += 1
            print(f"\n--- Keyword '{kw}' — page {pages}, {len(page)} results ---")
            for a in page:
                key = a.get("did") or a.get("handle")
                if not key or key in seen:
                    continue
                seen.add(key)

                text = combine_bio_desc(a)
                if kw not in (text.lower() if text else ""):
                    continue

                if (a.get("viewer") or {}).get("following") or key in session_followed:
                    continue

                display = a.get("displayName") or a.get("handle") or a.get("did") or "<unknown>"
                handle_or_did = a.get("handle") or a.get("did") or "<unknown>"

                print("=" * 72)
                print(f"{display}  (@{handle_or_did})")
                print(f"Bio/Description: {text if text else '(no description)'}")
                print(f"Matched keyword: {kw}")
                print("Follow this account? [y/N]: ", end="", flush=True)
                choice = sys.stdin.readline().strip().lower()
                if choice == "y":
                    subject_did = a.get("did")
                    if not subject_did:
                        print("No DID for actor; cannot follow.")
                        skipped += 1
                        continue
                    session_followed.add(subject_did)
                    if args.dry_run:
                        print("[dry-run] Would follow (create record).")
                        added += 1
                    else:
                        try:
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
    Depth-based exploration (batched, streaming):
      - Seeds streamed from your 'follows' in batches of --limit.
      - Only seeds whose bio/description matches any keyword are expanded.
      - For each matching seed, stream ONE page of its followers (size --limit) and prompt to follow.
      - If you follow someone and depth < --degreelimit, enqueue that account as a new seed.
    Prints per-100-account stats to STDERR.
    """
    if not keywords:
        print("No keywords provided; nothing to match.", file=sys.stderr)
        return

    max_depth = max(1, int(args.degreelimit))
    batch_size = max(1, args.limit)

    print(f"Exploring up to depth (--degreelimit) = {max_depth}. Batch size (--limit) = {batch_size}.")

    # Stats that report every 100 follower-accounts processed
    STATS_BATCH_N = 100

    class Stats:
        def __init__(self, n=STATS_BATCH_N):
            self.n = n
            self.cum = Counter()
            self.block = Counter()

        def _b(self, k, inc=1):
            self.block[k] = self.block.get(k, 0) + inc
            self.cum[k] = self.cum.get(k, 0) + inc

        def account_seen(self):
            self._b("followers_iterated", 1)
            if self.block.get("followers_iterated", 0) >= self.n:
                self.report_block()
                self.block = Counter()

        def seed_seen(self): self._b("seeds_seen", 1)
        def seed_matched(self): self._b("seeds_matched", 1)

        def no_key_skip(self): self._b("no_key_skip", 1)
        def self_skip(self): self._b("self_skip", 1)
        def already_following_skip(self): self._b("already_following_skip", 1)
        def dedup_skip(self): self._b("dedup_skip", 1)
        def keyword_miss(self): self._b("keyword_miss", 1)

        def candidate(self): self._b("candidates_considered", 1); self._b("prompted", 1)
        def followed(self): self._b("followed_added", 1)
        def declined(self): self._b("user_declined", 1)
        def no_did_skip(self): self._b("no_did_skip", 1)
        def api_error(self): self._b("api_error", 1)
        def enqueued(self): self._b("enqueued_new_seeds", 1)

        def _format(self, d):
            skipped = d.get("keyword_miss",0)+d.get("already_following_skip",0)+d.get("dedup_skip",0)+d.get("self_skip",0)+d.get("no_key_skip",0)
            lines = [
                f"  Followers processed: {d.get('followers_iterated',0)}  (skipped: {skipped})",
                f"    - keyword_miss={d.get('keyword_miss',0)}, already_following={d.get('already_following_skip',0)}, dedup={d.get('dedup_skip',0)}, self={d.get('self_skip',0)}, no_key={d.get('no_key_skip',0)}",
                f"  Candidates prompted: {d.get('prompted',0)}",
                f"    - followed={d.get('followed_added',0)}, declined={d.get('user_declined',0)}, no_did={d.get('no_did_skip',0)}, api_error={d.get('api_error',0)}, enqueued_new_seeds={d.get('enqueued_new_seeds',0)}",
                f"  Seeds: seen={d.get('seeds_seen',0)}, matched={d.get('seeds_matched',0)}",
            ]
            return '\n'.join(lines)

        def report_block(self):
            sys.stderr.write('\n[degreesearch] Stats for last %d accounts:\n' % self.n)
            sys.stderr.write(self._format(self.block) + '\n')
            sys.stderr.write('[degreesearch] Cumulative so far:\n')
            sys.stderr.write(self._format(self.cum) + '\n')
            sys.stderr.flush()

    stats = Stats()

    def seed_matches(obj):
        return matches_any_keyword(combine_bio_desc(obj), keywords)

    # Stream seeds from your follows
    seed_source = iter_follows(service, access, handle, batch_size=batch_size, max_pages=10000)
    seed_buffer = deque()
    queue = deque()
    visited_seeds = set()
    seen_candidates = set()
    session_followed = set()
    added, skipped = 0, 0
    source_exhausted = False
    current_seed_batch_idx = 0

    def key_of(obj):
        return obj.get("did") or obj.get("handle")

    def refill_seeds():
        nonlocal source_exhausted, current_seed_batch_idx
        if source_exhausted:
            return False
        try:
            follows_batch = next(seed_source)
        except StopIteration:
            source_exhausted = True
            return False
        current_seed_batch_idx += 1
        print(f"\n--- Seed batch {current_seed_batch_idx} (size={len(follows_batch)}) ---")
        for s in follows_batch:
            seed_buffer.append(s)
        return True

    if not refill_seeds() and not seed_buffer:
        print("You do not follow anyone (or no data returned).")
        return

    while True:
        while seed_buffer and len(queue) < batch_size:
            seed = seed_buffer.popleft()
            k = key_of(seed)
            if not k or k in visited_seeds:
                continue
            stats.seed_seen()
            if not seed_matches(seed):
                continue
            stats.seed_matched()
            queue.append((seed, 0))

        if not queue:
            if refill_seeds():
                continue
            break

        seed, depth = queue.popleft()
        k = key_of(seed)
        if not k or k in visited_seeds:
            continue
        visited_seeds.add(k)

        # Enforce keyword match at all depths before expanding this seed
        if not seed_matches(seed):
            # Not a keyword match anymore (or never was) — skip expanding
            continue

        seed_handle_or_did = seed.get("handle") or seed.get("did") or "<unknown>"
        seed_text = combine_bio_desc(seed)
        print("=" * 72)
        print(f"Seed (depth {depth}): {seed.get('displayName') or seed_handle_or_did} (@{seed_handle_or_did})")
        print(f"Bio/Description: {seed_text if seed_text else '(no description)'}")

        if depth >= max_depth:
            print("(Reached max depth for this branch; not expanding followers.)")
            continue

        # Fetch one page of followers for this seed
        follower_pages = iter_followers(service, access, seed_handle_or_did, batch_size=batch_size, max_pages=1)
        for followers in follower_pages:
            print(f"  Followers page — {len(followers)} accounts to review at depth {depth+1}.")
            for f in followers:
                stats.account_seen()
                f_key = key_of(f)
                if not f_key:
                    stats.no_key_skip(); continue
                if f_key in seen_candidates:
                    stats.dedup_skip(); continue
                if f_key == did:
                    stats.self_skip(); continue
                if (f.get('viewer') or {}).get('following') or f_key in session_followed:
                    stats.already_following_skip(); continue

                f_text = combine_bio_desc(f)
                if not matches_any_keyword(f_text, keywords):
                    stats.keyword_miss(); continue

                seen_candidates.add(f_key)
                display = f.get("displayName") or f.get("handle") or f.get("did") or "<unknown>"
                handle_or_did = f.get("handle") or f.get("did") or "<unknown>"
                print("-" * 72)
                print(f"Candidate (depth {depth+1}): {display}  (@{handle_or_did})  — follower of seed above")
                print(f"Bio/Description: {f_text if f_text else '(no description)'}")
                print("Follow this account? [Y/n]: ", end="", flush=True)
                stats.candidate()
                choice = sys.stdin.readline().strip().lower()

                if choice in ("", "y", "yes"):
                    subject_did = f.get("did")
                    if not subject_did:
                        print("No DID for actor; cannot follow.")
                        stats.no_did_skip(); skipped += 1
                    else:
                        session_followed.add(subject_did)
                        if args.dry_run:
                            print("[dry-run] Would follow (create record).")
                            stats.followed(); added += 1
                            if depth + 1 <= max_depth - 1 and seed_matches(f):
                                queue.append((f, depth + 1)); stats.enqueued()
                        else:
                            try:
                                create_follow_record(service, access, did, subject_did)
                                print("Followed.")
                                stats.followed(); added += 1
                                if depth + 1 <= max_depth - 1 and seed_matches(f):
                                    queue.append((f, depth + 1)); stats.enqueued()
                            except Exception as e:
                                print(f"Failed to follow: {e}")
                                stats.api_error(); skipped += 1
                else:
                    stats.declined(); skipped += 1
                    print("Skipped.")

    print("\nDone.")
    print(f"New follows added this session: {added}")
    print(f"Skipped: {skipped}")
    if args.dry_run:
        print("NOTE: dry-run mode; no changes were made.")

def mode_wordmap(args, service, access, did, handle):
    use_following = bool(getattr(args, "wordmap_following", False))
    use_followers = bool(getattr(args, "wordmap_followers", False))
    if use_following == use_followers:
        print("Please specify exactly one of --following or --followers for wordmap mode.", file=sys.stderr)
        return

    batch_size = max(1, args.limit)
    token_re = re.compile(r"[A-Za-z0-9]+")
    stopwords = {
        "the","and","for","you","your","with","are","that","this","from","have","has","was","were","but","not","all",
        "our","about","into","out","over","under","on","in","of","to","a","an","as","by","at","it","we","they","them",
        "be","is","am","or","if","so","my","me","their","his","her","he","she","i","us","rt"
    }

    counts = Counter()
    processed = 0

    if use_followers:
        print("Streaming your followers for wordmap ...")
        iterator = iter_followers(service, access, handle, batch_size=batch_size, max_pages=10000)
    else:
        print("Streaming your follows for wordmap ...")
        iterator = iter_follows(service, access, handle, batch_size=batch_size, max_pages=10000)

    batch_idx = 0
    for people in iterator:
        batch_idx += 1
        print(f"  Batch {batch_idx} (size={len(people)})")
        for p in people:
            text = combine_bio_desc(p)
            if not text:
                continue
            for tok in token_re.findall(text.lower()):
                if len(tok) < 3: continue
                if tok in stopwords: continue
                counts[tok] += 1
            processed += 1
            if processed % 500 == 0:
                sys.stderr.write("."); sys.stderr.flush()

    if processed >= 500:
        sys.stderr.write("\n"); sys.stderr.flush()

    if not counts:
        print("No words found in bios/descriptions.")
        return

    print("\nWord frequency (descending):")
    for word, cnt in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"{word}\t{cnt}")

def mode_listify(args, service, access, did, handle, keywords):
    """
    Create a Bluesky List from accounts you ALREADY FOLLOW whose bio/description
    contains any keyword from --keywords. The list name is the sorted, de-duplicated
    keywords joined with '/', trimmed to 64 characters (with '/+N' overflow marker).
    In this batched version, --limit controls the API *batch size*; we scan all follows.
    """
    if not keywords:
        print("listify requires --keywords <file.txt> with one keyword per line.", file=sys.stderr)
        return

    kwset = {kw.lower() for kw in keywords if kw}
    list_name = _build_list_name_from_keywords(keywords, max_len=64)
    purpose = "app.bsky.graph.defs#modlist" if getattr(args, "modlist", False) else "app.bsky.graph.defs#curatelist"
    desc = f"Auto-curated list from keywords: {', '.join(sorted(kwset))}"

    # Pass 1: stream your follows and collect matches (we need counts before creating the list in dry-run)
    print("Scanning your follows for keyword matches (streaming in batches) ...")
    batch_size = max(1, args.limit)
    matches = []
    total_seen = 0
    batch_idx = 0
    for follows in iter_follows(service, access, handle, batch_size=batch_size, max_pages=10000):
        batch_idx += 1
        print(f"  Batch {batch_idx} (size={len(follows)})")
        for p in follows:
            total_seen += 1
            text = (combine_bio_desc(p) or "").lower()
            if any(k in text for k in kwset):
                matches.append(p)

            if total_seen % 500 == 0:
                sys.stderr.write("."); sys.stderr.flush()
    if total_seen >= 500:
        sys.stderr.write("\n"); sys.stderr.flush()

    print("=" * 72)
    print(f"List name: {list_name}")
    print(f"Purpose: {'moderation (modlist)' if getattr(args, 'modlist', False) else 'curation (curatelist)'}")
    print(f"Matches to add: {len(matches)} (from {total_seen} follows reviewed)")

    if args.dry_run:
        print("[dry-run] Would create list and add these handles/DIDs:")
        for p in matches:
            print(" -", p.get("handle") or p.get("did"))
        print("[dry-run] No changes were made.")
        return

    # Create the list
    try:
        res = create_list_record(service, access, did, name=list_name, purpose=purpose, description=desc)
        list_uri = res.get("uri")
        if not list_uri:
            raise RuntimeError("List creation did not return a URI.")
        print(f"Created list: {list_uri}")
    except Exception as e:
        print(f"Failed to create list: {e}")
        return

    # Add members
    added, failed = 0, 0
    for p in matches:
        subject_did = p.get("did")
        if not subject_did:
            failed += 1
            print(f"Skip (no DID): {p.get('handle') or '<unknown>'}")
            continue
        try:
            create_listitem_record(service, access, did, list_uri, subject_did)
            added += 1
            if added % 50 == 0:
                sys.stderr.write("."); sys.stderr.flush()
        except Exception as e:
            failed += 1
            print(f"\nFailed to add {p.get('handle') or subject_did}: {e}")

    if added >= 50:
        sys.stderr.write("\n"); sys.stderr.flush()

    print("\nDone.")
    print(f"List: {list_name}")
    print(f"Added: {added}")
    print(f"Failed: {failed}")


# ------------------------- main -------------------------
def main():
    ap = argparse.ArgumentParser(description="Audit / discover follows on Bluesky (batched).")
    ap.add_argument("-m", "--mode", choices=["following","searching","degreesearch","wordmap","listify"], default="following",
                    help="Mode: 'following', 'searching', 'degreesearch', or 'wordmap'.")
    ap.add_argument("--creds", required=True, help="Path to file: line1=<handle>, line2=<app_password>")
    ap.add_argument("--keywords", required=False, help="(Optional) Path to newline-separated keywords (case-insensitive). Not used in 'wordmap' mode.")
    ap.add_argument("--service", default="https://bsky.social", help="PDS base URL (default: https://bsky.social)")
    ap.add_argument("--limit", type=int, default=100, help="*Batch size* for API pagination in all modes.")
    ap.add_argument("--degreelimit", type=int, default=1,
                    help="For degreesearch: maximum DEPTH (levels) to explore from your seeds (min 1).")
    ap.add_argument("--dry-run", action="store_true", help="Don’t actually change follows; just show what would happen")
    ap.add_argument("--nodesc", action="store_true", help="(following mode) Auto-review empty descriptions within each batch.")
    ap.add_argument("--modlist", action="store_true", help="(listify) Create a moderation list (purpose=app.bsky.graph.defs#modlist) instead of a curated list (curatelist).")
    ap.add_argument("--following", dest="wordmap_following", action="store_true", default=False,
                    help="(wordmap mode) Analyze accounts you follow.")
    ap.add_argument("--followers", dest="wordmap_followers", action="store_true", default=False,
                    help="(wordmap mode) Analyze accounts that follow you.")

    args = ap.parse_args()

    handle, app_password = read_creds(Path(args.creds))
    keywords = []
    if args.keywords and args.mode != "wordmap":
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
    elif args.mode == "listify":
        mode_listify(args, args.service, access, did, confirmed_handle, keywords)
    elif args.mode == "wordmap":
        mode_wordmap(args, args.service, access, did, confirmed_handle)
    else:
        mode_degreesearch(args, args.service, access, did, confirmed_handle, keywords)

if __name__ == "__main__":
    main()
