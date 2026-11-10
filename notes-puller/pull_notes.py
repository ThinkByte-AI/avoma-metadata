#!/usr/bin/env python3
"""
Pull Avoma **AI Notes / summary** for the 10 people's meetings, deduped.

Work-list: union of data/metadata/meetings_<person>.csv for the 10 people, keep each
unique transcript-ready meeting once. AI notes are generated from the transcript,
so transcript_ready=True is the gate (~3,109 meetings).

Per meeting we call  GET /v1/notes?meeting_uuid=<uuid>  with an attending
person's API key, and save:
    data/notes/<uuid>.json   raw Avoma response (rich-text block format)
    data/notes/<uuid>.md     flattened, human-readable summary
Plus data/notes/notes_index.csv mapping uuid -> subject/start/owner_used/attendees.

Gentle + resumable (mirrors archiver/pull_deduped_to_s3.py): single global ~30 req/min
clock with jitter, long backoff on 403(WAF)/429/5xx, and any meeting whose
data/notes/<uuid>.json already exists is skipped -- Ctrl-C and re-run any time.

Optional --sentiments also pulls GET /v1/meeting_sentiments -> data/sentiments/<uuid>.json.

Usage (run from the repo root):
    python notes-puller/pull_notes.py --dry-run          # show plan, no API calls
    python notes-puller/pull_notes.py --limit 3          # smoke test first 3
    python notes-puller/pull_notes.py                     # full run (~3,100 calls, resumable)
    python notes-puller/pull_notes.py --sentiments        # also archive sentiment timelines
"""
import argparse
import csv
import json
import os
import random
import sys
import time

import requests

KEYS_FILE = os.environ.get("KEYS_FILE", "avoma api key.txt")
BASE = os.environ.get("AVOMA_BASE_URL", "https://api.avoma.com/v1")
OUT_DIR = os.environ.get("NOTES_DIR", os.path.join("data", "notes"))
SENT_DIR = os.environ.get("SENT_DIR", os.path.join("data", "sentiments"))
INDEX = os.environ.get("NOTES_INDEX", os.path.join("data", "notes", "notes_index.csv"))
PROGRESS_LOG = os.environ.get("NOTES_LOG", "notes_progress.log")

# --- S3 (notes land beside the existing transcripts/recordings) ---
S3_BUCKET = os.environ.get("S3_BUCKET", "avoma-archive-growthbyte")
S3_PREFIX = os.environ.get("S3_PREFIX", "avoma").strip("/")
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
NOTES_STORAGE_CLASS = os.environ.get("NOTES_STORAGE_CLASS", "STANDARD")


def load_dotenv(path=".env"):
    """Make boto3 creds available without exporting them by hand."""
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

PEOPLE = ["Harsha", "charan", "Kalyan", "Raghu", "Bodhi",
          "charith", "Vinay", "abhilash", "samarpith", "yash"]

AVOMA_RPM = float(os.environ.get("AVOMA_RPM", "30"))   # GLOBAL, gentle
MIN_GAP = 60.0 / AVOMA_RPM
_last = [0.0]


# --------------------------------------------------------------------------- #
# Throttle + backoff (single global clock, like pull_deduped_to_s3.py)
# --------------------------------------------------------------------------- #
def _throttle():
    wait = MIN_GAP - (time.monotonic() - _last[0])
    if wait > 0:
        time.sleep(wait)
    time.sleep(random.uniform(0.0, 0.4))   # jitter so it doesn't look robotic
    _last[0] = time.monotonic()


def avoma_get(session, url, params=None, max_retries=6):
    """Returns parsed JSON, or None on a clean 404 (no notes for this meeting)."""
    for attempt in range(max_retries):
        _throttle()
        try:
            resp = session.get(url, params=params, timeout=60)
        except requests.RequestException as e:
            wait = min(5 * (2 ** attempt), 120)
            print(f"    [net] {e}; retry in {wait}s", file=sys.stderr)
            time.sleep(wait)
            continue
        sc = resp.status_code
        if sc == 200:
            # a stray HTML 200 would not parse; treat as miss
            try:
                return resp.json()
            except ValueError:
                return None
        if sc == 404:
            return None
        if sc in (429, 403) or sc >= 500:
            base = 30 if sc == 403 else 5     # 403 == IP WAF -> back off hardest
            wait = min(base * (2 ** attempt), 300)
            ra = resp.headers.get("Retry-After")
            if ra and ra.isdigit():
                wait = max(wait, int(ra))
            print(f"    [{'WAF/403' if sc==403 else sc}] backoff {wait}s "
                  f"({attempt+1}/{max_retries})", file=sys.stderr)
            time.sleep(wait)
            continue
        resp.raise_for_status()
    raise RuntimeError(f"give up {url}")


# --------------------------------------------------------------------------- #
# Keys + work-list
# --------------------------------------------------------------------------- #
def load_keys(path):
    """'Harsha-n70juqelin:secret' -> name 'Harsha', token 'n70juqelin:secret'."""
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            name, _, token = line.partition("-")
            out[name.strip()] = token.strip()
    return out


def build_worklist():
    """uuid -> {subject, start, owners:[people with transcript-ready]} deduped."""
    work = {}
    for p in PEOPLE:
        path = os.path.join("data", "metadata", f"meetings_{p}.csv")
        if not os.path.exists(path):
            print(f"WARN missing {path}", file=sys.stderr)
            continue
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("transcript_ready") != "True":
                    continue
                u = r["uuid"]
                e = work.setdefault(u, {"subject": r.get("subject", ""),
                                        "start": r.get("start", ""),
                                        "owners": []})
                e["owners"].append(p)
    # balance: primary owner = least-loaded among this meeting's attendees
    load = {p: 0 for p in PEOPLE}
    rows = []
    for u, e in sorted(work.items(), key=lambda kv: kv[1]["start"]):
        owners = e["owners"]
        primary = min(owners, key=lambda p: load[p])
        load[primary] += 1
        ordered = [primary] + [o for o in owners if o != primary]
        rows.append((u, e["subject"], e["start"], ordered))
    return rows, load


def write_worklist(path, rows):
    """Persist the computed work-list so a cloud run needs only this one small
    file (not the 10 per-person CSVs). owners are pipe-joined, primary first."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["uuid", "start", "subject", "owners"])
        for u, subj, start, owners in rows:
            w.writerow([u, start, subj, "|".join(owners)])


def load_worklist(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            owners = [o for o in r["owners"].split("|") if o]
            rows.append((r["uuid"], r["subject"], r["start"], owners))
    return rows


# --------------------------------------------------------------------------- #
# Render Avoma rich-text blocks -> markdown
# --------------------------------------------------------------------------- #
def _render_node(node, depth=0):
    if isinstance(node, list):
        return "".join(_render_node(n, depth) for n in node)
    if not isinstance(node, dict):
        return ""
    if "text" in node and node.get("object") == "text":
        return node["text"]
    t = node.get("type")
    inner = _render_node(node.get("children", []), depth + 1)
    if t == "header-1":
        return f"\n# {inner.strip()}\n"
    if t == "header-2":
        return f"\n## {inner.strip()}\n"
    if t == "header-3":
        return f"\n### {inner.strip()}\n"
    if t == "list-item":
        return f"{'  ' * max(0, depth - 1)}- {inner.strip()}\n"
    if t == "paragraph":
        return f"{inner.strip()}\n"
    return inner


def notes_to_markdown(payload, subject, start):
    out = [f"# {subject or 'Untitled'}", f"_{start}_", ""]
    results = payload.get("results", []) if isinstance(payload, dict) else []
    if not results:
        out.append("_(no AI notes generated for this meeting)_")
    for res in results:
        out.append(_render_node(res.get("data", [])))
    text = "\n".join(out)
    # collapse runs of blank lines
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.strip() + "\n"


# --------------------------------------------------------------------------- #
# S3 (optional) -- notes land at <prefix>/<YYYY>/<MM>/<uuid>/notes.{json,md}
# --------------------------------------------------------------------------- #
def s3_base_key(uuid, start):
    ym = start[:7].replace("-", "/") if len(start) >= 7 else "unknown"
    return f"{S3_PREFIX}/{ym}/{uuid}"


def s3_exists(s3, key):
    from botocore.exceptions import ClientError
    try:
        s3.head_object(Bucket=S3_BUCKET, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def s3_put(s3, key, body, content_type):
    if isinstance(body, str):
        body = body.encode("utf-8")
    s3.put_object(Bucket=S3_BUCKET, Key=key, Body=body,
                  ContentType=content_type, StorageClass=NOTES_STORAGE_CLASS)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="Pull Avoma AI notes for the 10 people")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sentiments", action="store_true",
                    help="also pull /meeting_sentiments -> sentiments/<uuid>.json")
    ap.add_argument("--no-md", action="store_true", help="skip the .md render")
    ap.add_argument("--s3", action="store_true",
                    help="upload notes.json + notes.md to S3 (resume off S3); "
                         "reuses already-downloaded local notes (no API cost)")
    ap.add_argument("--keep-local", action="store_true",
                    help="with --s3, also keep writing local data/notes/<uuid>.* files")
    ap.add_argument("--worklist", default="",
                    help="read the meeting work-list from this CSV (uuid,start,"
                         "subject,owners) instead of the 10 per-person CSVs; if "
                         "the path is missing it is built and written there")
    args = ap.parse_args()

    s3 = None
    if args.s3:
        import boto3
        load_dotenv()
        s3 = boto3.client("s3", region_name=AWS_REGION)

    keys = load_keys(KEYS_FILE)
    missing = [p for p in PEOPLE if p not in keys]
    if missing:
        sys.exit(f"keys missing for {missing} in {KEYS_FILE}")

    if args.worklist and os.path.exists(args.worklist):
        rows, load = load_worklist(args.worklist), None
    else:
        rows, load = build_worklist()
        if args.worklist:
            write_worklist(args.worklist, rows)
            print(f"Wrote work-list -> {args.worklist}")
    if args.limit:
        rows = rows[:args.limit]
    print(f"Work-list : {len(rows)} unique transcript-ready meetings")
    print(f"Rate cap  : {AVOMA_RPM:.0f} calls/min (~{MIN_GAP:.1f}s apart) + jitter")
    if args.s3:
        print(f"Out       : s3://{S3_BUCKET}/{S3_PREFIX}/<YYYY>/<MM>/<uuid>/notes.json (+.md)"
              f"   ({NOTES_STORAGE_CLASS}, region {AWS_REGION})")
        print(f"            local notes already downloaded are re-used (no API call)")
    else:
        print(f"Out       : {OUT_DIR}/<uuid>.json (+.md)"
              + (f"  sentiments/<uuid>.json" if args.sentiments else ""))
    est = len(rows) * (2 if args.sentiments else 1) / AVOMA_RPM
    print(f"Est. time : ~{est:.0f} min for a fresh full run\n")

    if args.dry_run:
        for i, (u, subj, start, owners) in enumerate(rows[:30], 1):
            print(f"[{i}] {start[:10]} {subj[:50]:50} {u} key={owners[0]}")
        if len(rows) > 30:
            print(f"... +{len(rows)-30} more")
        if load:
            print(f"\nLoad balance across keys: "
                  + " ".join(f"{p}:{load[p]}" for p in PEOPLE))
        print("DRY RUN: no API calls made.")
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    if args.sentiments:
        os.makedirs(SENT_DIR, exist_ok=True)

    sessions = {}

    def session_for(name):
        if name not in sessions:
            s = requests.Session()
            s.headers.update({"Authorization": "Bearer " + keys[name]})
            sessions[name] = s
        return sessions[name]

    n_done = n_skip = n_notes = n_empty = n_sent = n_err = 0
    log = open(PROGRESS_LOG, "a", encoding="utf-8")
    os.makedirs(os.path.dirname(INDEX) or ".", exist_ok=True)
    index = open(INDEX, "w", newline="", encoding="utf-8")
    iw = csv.writer(index)
    iw.writerow(["uuid", "start", "subject", "owner_used", "attendees",
                 "has_notes"])

    for i, (uuid, subject, start, owners) in enumerate(rows, 1):
        jpath = os.path.join(OUT_DIR, f"{uuid}.json")
        base = s3_base_key(uuid, start) if args.s3 else None
        print(f"[{i}/{len(rows)}] {start[:10]} {subject[:50]}  ({uuid})")

        # ---- resume: skip if destination already has it ----
        if args.s3:
            if s3_exists(s3, f"{base}/notes.json"):
                n_skip += 1
                iw.writerow([uuid, start, subject, "", "|".join(owners), None])
                continue
        elif os.path.exists(jpath):
            n_skip += 1
            has = None
            try:
                has = bool(json.load(open(jpath, encoding="utf-8")).get("results"))
            except Exception:
                pass
            iw.writerow([uuid, start, subject, "", "|".join(owners), has])
            continue

        # ---- obtain payload: prefer an already-downloaded local file (no API
        #      call), else pull from the API via a balanced key + fallbacks ----
        payload, used = None, ""
        if os.path.exists(jpath):
            try:
                payload = json.load(open(jpath, encoding="utf-8"))
                used = "local"
            except Exception:
                payload = None
        if payload is None:
            for name in owners:
                try:
                    payload = avoma_get(session_for(name), f"{BASE}/notes",
                                        params={"meeting_uuid": uuid})
                except Exception as e:
                    print(f"    notes ERROR via {name}: {e}", file=sys.stderr)
                    payload = None
                if payload is not None:
                    used = name
                    break

        if payload is None:
            n_err += 1
            log.write(f"NONE\t{uuid}\t{owners}\n"); log.flush()
            iw.writerow([uuid, start, subject, "", "|".join(owners), False])
            continue

        has_notes = bool(payload.get("results"))
        if has_notes:
            n_notes += 1
        else:
            n_empty += 1
        md = None if args.no_md else notes_to_markdown(payload, subject, start)

        # ---- persist to S3 and/or local ----
        if args.s3:
            s3_put(s3, f"{base}/notes.json",
                   json.dumps(payload, ensure_ascii=False, indent=2),
                   "application/json")
            if md is not None:
                s3_put(s3, f"{base}/notes.md", md, "text/markdown; charset=utf-8")
        if (not args.s3) or args.keep_local:
            with open(jpath, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            if md is not None:
                with open(os.path.join(OUT_DIR, f"{uuid}.md"), "w",
                          encoding="utf-8") as f:
                    f.write(md)

        iw.writerow([uuid, start, subject, used, "|".join(owners), has_notes])
        log.write(f"NOTES\t{uuid}\t{used}\t{'has' if has_notes else 'empty'}\n")
        log.flush()

        # optional sentiments in the same pass
        if args.sentiments:
            skey = f"{base}/sentiment.json" if args.s3 else None
            spath = os.path.join(SENT_DIR, f"{uuid}.json")
            done = s3_exists(s3, skey) if args.s3 else os.path.exists(spath)
            if not done:
                # 'used' may be "local" (notes came from disk) -> pick a real key
                key_name = used if used in keys else owners[0]
                try:
                    sent = avoma_get(session_for(key_name),
                                     f"{BASE}/meeting_sentiments",
                                     params={"meeting_uuid": uuid})
                    if sent is not None:
                        body = json.dumps(sent, ensure_ascii=False, indent=2)
                        if args.s3:
                            s3_put(s3, skey, body, "application/json")
                        if (not args.s3) or args.keep_local:
                            with open(spath, "w", encoding="utf-8") as f:
                                f.write(body)
                        n_sent += 1
                except Exception as e:
                    print(f"    sentiment ERROR: {e}", file=sys.stderr)

        n_done += 1

    index.close()
    log.close()
    print("\n" + "=" * 60)
    print(f"Processed this run : {n_done}")
    print(f"Notes saved        : {n_notes} with content, {n_empty} empty")
    print(f"Skipped (existing) : {n_skip}")
    if args.sentiments:
        print(f"Sentiments saved   : {n_sent}")
    print(f"No-access/errors   : {n_err}")
    print(f"Index              : {INDEX}")
    if args.s3:
        print(f"S3 dest            : s3://{S3_BUCKET}/{S3_PREFIX}/<YYYY>/<MM>/<uuid>/notes.json")
    print("=" * 60)
    print("Re-run to resume; finished meetings are skipped.")


if __name__ == "__main__":
    main()
