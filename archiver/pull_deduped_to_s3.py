#!/usr/bin/env python3
"""
Sequentially archive the DEDUPED Avoma recordings (+ optional transcripts) to S3.

Reads meetings_deduped.csv (the unique set produced by dedup_cost.py) and pulls
each video-ready meeting ONE AT A TIME, gently, to stay well under Avoma's
60 req/min API limit and avoid its IP-level WAF. Fully resumable: anything
already present in your S3 bucket is skipped, so you can Ctrl-C and re-run.

Per meeting it uses the owning member's API key (from keys.txt) to fetch a fresh
short-lived signed URL, then streams the bytes straight into your S3 bucket --
the signed URL points at Avoma's storage/CDN, not the rate-limited API, so the
big transfer itself doesn't count against the API budget.

Config via environment (or a .env you load yourself):
  S3_BUCKET                 (required) destination bucket
  AWS_REGION                default ap-south-1
  S3_PREFIX                 default "avoma"
  VIDEO_STORAGE_CLASS       default GLACIER_IR
  TRANSCRIPT_STORAGE_CLASS  default STANDARD
  AVOMA_RPM                 default 30   (GLOBAL across all keys -- gentle)
  PULL_TRANSCRIPTS          default "1"  (set "0" to skip transcripts)
  AWS credentials via the standard boto3 chain (env vars / shared profile / role)

Usage:
  python pull_deduped_to_s3.py --dry-run      # show plan, no uploads, no Avoma calls
  python pull_deduped_to_s3.py --limit 3      # pull only the first 3 (smoke test)
  python pull_deduped_to_s3.py                # full run, sequential + resumable
"""
import argparse
import csv
import os
import random
import sys
import time

import boto3
import requests
from botocore.exceptions import ClientError

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
AVOMA_BASE_URL = os.environ.get("AVOMA_BASE_URL", "https://api.avoma.com/v1")
S3_BUCKET = os.environ.get("S3_BUCKET", "")
S3_PREFIX = os.environ.get("S3_PREFIX", "avoma").strip("/")
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
VIDEO_STORAGE_CLASS = os.environ.get("VIDEO_STORAGE_CLASS", "GLACIER_IR")
TRANSCRIPT_STORAGE_CLASS = os.environ.get("TRANSCRIPT_STORAGE_CLASS", "STANDARD")
PULL_TRANSCRIPTS = os.environ.get("PULL_TRANSCRIPTS", "1") == "1"

# GLOBAL rate cap (shared across every key, because the WAF is IP-based, not
# key-based). 30/min = one API call roughly every 2s -- comfortably gentle.
AVOMA_RPM = float(os.environ.get("AVOMA_RPM", "30"))
MIN_SECONDS_BETWEEN_CALLS = 60.0 / AVOMA_RPM

MANIFEST = os.environ.get("MANIFEST", "meetings_deduped.csv")
KEYS_FILE = os.environ.get("KEYS_FILE", "keys.txt")
PROGRESS_LOG = os.environ.get("PROGRESS_LOG", "pull_progress.log")

PRICE_PER_GB_MONTH = {
    "STANDARD": 0.023, "STANDARD_IA": 0.0125,
    "GLACIER_IR": 0.004, "GLACIER": 0.0036, "DEEP_ARCHIVE": 0.00099,
}

# --------------------------------------------------------------------------- #
# Gentle throttle + backoff (single global clock)
# --------------------------------------------------------------------------- #
_last_call = [0.0]


def _throttle():
    """Sleep so that no two Avoma API calls are closer than the cap, + jitter
    so the request pattern doesn't look like a metronome (WAF heuristics)."""
    elapsed = time.monotonic() - _last_call[0]
    wait = MIN_SECONDS_BETWEEN_CALLS - elapsed
    if wait > 0:
        time.sleep(wait)
    time.sleep(random.uniform(0.0, 0.4))  # jitter
    _last_call[0] = time.monotonic()


def avoma_get(session, url, params=None, max_retries=6):
    """Throttled GET with long, patient backoff. Treats 403 as a likely WAF
    block and backs off hard rather than hammering."""
    for attempt in range(max_retries):
        _throttle()
        resp = session.get(url, params=params, timeout=60)
        sc = resp.status_code
        if sc == 200:
            return resp.json()
        if sc == 404:
            return None
        if sc == 429 or sc == 403 or sc >= 500:
            # 403 with an HTML body == IP WAF -> back off the longest.
            base = 30 if sc == 403 else 5
            wait = min(base * (2 ** attempt), 300)
            ra = resp.headers.get("Retry-After")
            if ra and ra.isdigit():
                wait = max(wait, int(ra))
            label = "WAF/403" if sc == 403 else str(sc)
            print(f"    [{label}] backing off {wait}s (attempt {attempt+1}/{max_retries})...",
                  file=sys.stderr)
            time.sleep(wait)
            continue
        resp.raise_for_status()
    raise RuntimeError(f"Giving up on {url} after {max_retries} retries")


# --------------------------------------------------------------------------- #
# Avoma helpers
# --------------------------------------------------------------------------- #
def get_recording(session, meeting_uuid):
    data = avoma_get(session, f"{AVOMA_BASE_URL}/recordings",
                     params={"meeting_uuid": meeting_uuid})
    if isinstance(data, dict) and "results" in data:
        results = data["results"]
        return results[0] if results else None
    return data


def get_transcript(session, meeting_uuid):
    return avoma_get(session, f"{AVOMA_BASE_URL}/transcriptions",
                     params={"meeting_uuid": meeting_uuid})


def recording_urls(recording):
    """Return EVERY downloadable asset on the recording object as (url, kind).
    Avoma may expose a video URL and a separate audio URL -- we grab BOTH."""
    if not recording:
        return []
    out = []
    video = recording.get("video_url") or recording.get("url")
    if video:
        out.append((video, "video"))
    if recording.get("audio_url"):
        out.append((recording["audio_url"], "audio"))
    return out


# --------------------------------------------------------------------------- #
# S3 helpers
# --------------------------------------------------------------------------- #
def s3_object_exists(s3, bucket, key):
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def stream_url_to_s3(s3, url, bucket, key, storage_class):
    """Stream the signed-URL download straight into S3 (multipart). NOT
    throttled -- this hits storage/CDN, not the rate-limited API."""
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        r.raw.decode_content = True
        size = int(r.headers.get("Content-Length", 0))
        s3.upload_fileobj(r.raw, bucket, key,
                          ExtraArgs={"StorageClass": storage_class})
    if not size:
        size = s3.head_object(Bucket=bucket, Key=key)["ContentLength"]
    return size


def put_json(s3, bucket, key, obj, storage_class):
    import json
    body = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
    s3.put_object(Bucket=bucket, Key=key, Body=body,
                  ContentType="application/json", StorageClass=storage_class)
    return len(body)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def load_keys():
    keymap = {}
    with open(KEYS_FILE, encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 2:
                keymap[parts[0]] = parts[1]
    return keymap


def load_rows():
    """Every unique meeting that has ANY asset: video, audio (implied by a
    recording), or a transcript. We fetch the recording object for all of them
    so audio-only meetings aren't missed."""
    rows = []
    with open(MANIFEST, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("video_ready") == "True" or r.get("transcript_ready") == "True":
                rows.append(r)
    # oldest first -> stable, resumable order
    rows.sort(key=lambda r: r.get("start", ""))
    return rows


def main():
    ap = argparse.ArgumentParser(description="Sequentially archive deduped Avoma recordings to S3")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show the plan; make NO Avoma calls and NO uploads")
    ap.add_argument("--limit", type=int, default=0, help="Process only the first N (smoke test)")
    ap.add_argument("--no-transcripts", action="store_true", help="Skip transcripts this run")
    args = ap.parse_args()

    pull_tx = PULL_TRANSCRIPTS and not args.no_transcripts

    rows = load_rows()
    if args.limit:
        rows = rows[:args.limit]
    print(f"Manifest: {len(rows)} unique meetings with video/audio/transcript to consider")
    print(f"Rate cap: {AVOMA_RPM:.0f} API calls/min (~{MIN_SECONDS_BETWEEN_CALLS:.1f}s apart) + jitter")
    print(f"Dest    : s3://{S3_BUCKET}/{S3_PREFIX}/  region {AWS_REGION}  "
          f"video={VIDEO_STORAGE_CLASS} transcript={TRANSCRIPT_STORAGE_CLASS}")
    print(f"Transcripts: {'yes' if pull_tx else 'no'}\n")

    if args.dry_run:
        for i, r in enumerate(rows, 1):
            print(f"[{i}] {r.get('start','')[:10]}  {r.get('subject','')[:55]}  ({r['uuid']}) key={r.get('owner_key')}")
        print(f"\nDRY RUN: would pull up to {len(rows)} recordings. No calls made.")
        return

    if not S3_BUCKET:
        sys.exit("S3_BUCKET is not set. Set it (and AWS creds/region) then re-run.")

    keymap = load_keys()
    s3 = boto3.client("s3", region_name=AWS_REGION)
    sessions = {}  # owner_key -> requests.Session with that bearer token

    def session_for(owner_key):
        if owner_key not in sessions:
            tok = keymap.get(owner_key)
            if not tok:
                return None
            s = requests.Session()
            s.headers.update({"Authorization": f"Bearer {tok}"})
            sessions[owner_key] = s
        return sessions[owner_key]

    n_done = n_skipped = n_assets = n_transcripts = n_err = 0
    asset_bytes = transcript_bytes = 0
    log = open(PROGRESS_LOG, "a", encoding="utf-8")

    for i, r in enumerate(rows, 1):
        uuid = r["uuid"]
        owner_key = r.get("owner_key", "")
        start = r.get("start", "")
        ym = start[:7].replace("-", "/") if len(start) >= 7 else "unknown"
        base = f"{S3_PREFIX}/{ym}/{uuid}"
        subject = (r.get("subject") or "untitled").strip()
        print(f"[{i}/{len(rows)}] {start[:10]}  {subject[:55]}  ({uuid})")

        session = session_for(owner_key)
        if session is None:
            print(f"    SKIP: no API key for owner '{owner_key}' in {KEYS_FILE}", file=sys.stderr)
            n_err += 1
            continue

        # ---- recordings: video AND audio, whichever exist ----
        ext_for = {"video": "mp4", "audio": "mp3"}
        keys_for = {k: f"{base}/recording.{ext_for[k]}" for k in ext_for}
        need = {k for k, key in keys_for.items() if not s3_object_exists(s3, S3_BUCKET, key)}
        if not need:
            print("    recording: video+audio already in S3, skip")
            n_skipped += 1
        elif r.get("video_ready") == "True":
            try:
                recording = get_recording(session, uuid)
                assets = recording_urls(recording)
                if not assets:
                    print("    recording: none available")
                for url, kind in assets:
                    if kind not in need:
                        continue
                    key = keys_for[kind]
                    try:
                        n = stream_url_to_s3(s3, url, S3_BUCKET, key, VIDEO_STORAGE_CLASS)
                    except requests.HTTPError as e:
                        # signed URL may have expired between fetch & stream; refetch once
                        if e.response is not None and e.response.status_code in (401, 403):
                            recording = get_recording(session, uuid)
                            url2 = dict((kk, uu) for uu, kk in recording_urls(recording)).get(kind)
                            if not url2:
                                raise
                            n = stream_url_to_s3(s3, url2, S3_BUCKET, key, VIDEO_STORAGE_CLASS)
                        else:
                            raise
                    asset_bytes += n
                    n_assets += 1
                    print(f"    {kind} ({n/1e6:.1f} MB) -> s3://{S3_BUCKET}/{key}")
                    log.write(f"{kind.upper()}\t{uuid}\t{n}\t{key}\n"); log.flush()
            except Exception as e:
                print(f"    recording ERROR: {e}", file=sys.stderr)
                log.write(f"ERROR\t{uuid}\t{e}\n"); log.flush()
                n_err += 1

        # ---- transcript (tiny) ----
        if pull_tx and r.get("transcript_ready") == "True":
            tkey = f"{base}/transcript.json"
            if s3_object_exists(s3, S3_BUCKET, tkey):
                pass  # already there
            else:
                try:
                    tx = get_transcript(session, uuid)
                    if tx is not None:
                        b = put_json(s3, S3_BUCKET, tkey, tx, TRANSCRIPT_STORAGE_CLASS)
                        transcript_bytes += b
                        n_transcripts += 1
                        print(f"    transcript -> s3://{S3_BUCKET}/{tkey}")
                except Exception as e:
                    print(f"    transcript ERROR: {e}", file=sys.stderr)

        n_done += 1

    log.close()
    gb_v = asset_bytes / 1e9
    mo_v = gb_v * PRICE_PER_GB_MONTH.get(VIDEO_STORAGE_CLASS, 0.004)
    print("\n" + "=" * 60)
    print(f"Processed            : {n_done}/{len(rows)}")
    print(f"Assets uploaded      : {n_assets} video+audio files  ({gb_v:.2f} GB)")
    print(f"Transcripts uploaded : {n_transcripts}  ({transcript_bytes/1e6:.1f} MB)")
    print(f"Skipped (in S3)      : {n_skipped}")
    print(f"Errors               : {n_err}")
    print(f"Est. recording cost  : ${mo_v:.2f}/mo ({VIDEO_STORAGE_CLASS})")
    print("=" * 60)
    print("Re-run the same command to retry errors / resume; finished objects are skipped.")


if __name__ == "__main__":
    main()
