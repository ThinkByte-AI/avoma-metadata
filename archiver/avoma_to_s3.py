#!/usr/bin/env python3
"""
Pull Avoma meeting recordings (video/audio) + transcripts and archive them to S3.

- Lists meetings in a date range (cursor-paginated)
- For each meeting: fetches the recording download URL and the transcript JSON
- Streams the video straight from Avoma -> S3 (no full file on local disk)
- Stores video in S3 Glacier Instant Retrieval (cheap, millisecond reads)
- Stores transcript JSON in S3 Standard (tiny, kept hot for easy querying)
- Idempotent / resumable: skips objects that already exist in the bucket
- Respects Avoma's 60 req/min rate limit and retries on 429/5xx
- Tracks bytes uploaded and prints a running S3 cost estimate

Usage:
    pip install -r requirements.txt
    # set env vars (see .env.example), then:
    python avoma_to_s3.py --from 2024-01-01 --to 2024-12-31

Auth: pass your Avoma API key in AVOMA_API_KEY. It is sent as `Authorization: Bearer <key>`.
AWS creds are picked up by boto3 from the usual chain (env vars, ~/.aws/credentials, IAM role).
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

import boto3
import requests
from botocore.exceptions import ClientError

# --------------------------------------------------------------------------- #
# Config (env vars)
# --------------------------------------------------------------------------- #
AVOMA_API_KEY = os.environ.get("AVOMA_API_KEY", "")
AVOMA_BASE_URL = os.environ.get("AVOMA_BASE_URL", "https://api.avoma.com/v1")
S3_BUCKET = os.environ.get("S3_BUCKET", "")
S3_PREFIX = os.environ.get("S3_PREFIX", "avoma").strip("/")
VIDEO_STORAGE_CLASS = os.environ.get("VIDEO_STORAGE_CLASS", "GLACIER_IR")  # Glacier Instant Retrieval
TRANSCRIPT_STORAGE_CLASS = os.environ.get("TRANSCRIPT_STORAGE_CLASS", "STANDARD")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# Avoma rate limit is 60 req/min. Stay comfortably under it.
MIN_SECONDS_BETWEEN_CALLS = 60.0 / float(os.environ.get("AVOMA_RPM", "55"))

# Rough $/GB/month for the running cost estimate (us-east-1 list prices).
PRICE_PER_GB_MONTH = {
    "STANDARD": 0.023,
    "STANDARD_IA": 0.0125,
    "GLACIER_IR": 0.004,      # Glacier Instant Retrieval
    "GLACIER": 0.0036,        # Glacier Flexible Retrieval
    "DEEP_ARCHIVE": 0.00099,
}

session = requests.Session()
session.headers.update({"Authorization": f"Bearer {AVOMA_API_KEY}"})
_last_call = [0.0]


def _throttle():
    elapsed = time.monotonic() - _last_call[0]
    if elapsed < MIN_SECONDS_BETWEEN_CALLS:
        time.sleep(MIN_SECONDS_BETWEEN_CALLS - elapsed)
    _last_call[0] = time.monotonic()


def avoma_get(url, params=None, max_retries=5):
    """GET against Avoma with throttling + exponential backoff on 429/5xx."""
    for attempt in range(max_retries):
        _throttle()
        resp = session.get(url, params=params, timeout=60)
        if resp.status_code == 429 or resp.status_code >= 500:
            wait = min(2 ** attempt, 30)
            retry_after = resp.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                wait = int(retry_after)
            print(f"  [{resp.status_code}] backing off {wait}s...", file=sys.stderr)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError(f"Giving up on {url} after {max_retries} retries")


# --------------------------------------------------------------------------- #
# Avoma API helpers
# --------------------------------------------------------------------------- #
def iter_meetings(from_date, to_date, page_size=100):
    """Yield meetings between two ISO dates, following cursor pagination."""
    url = f"{AVOMA_BASE_URL}/meetings"
    params = {"from_date": from_date, "to_date": to_date, "page_size": page_size}
    while url:
        data = avoma_get(url, params=params)
        for meeting in data.get("results", []):
            yield meeting
        url = data.get("next")   # full URL or null
        params = None            # `next` already encodes the params


def get_recording(meeting_uuid):
    """Return the recording object (contains a short-lived signed download URL)."""
    try:
        data = avoma_get(f"{AVOMA_BASE_URL}/recordings",
                         params={"meeting_uuid": meeting_uuid})
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return None
        raise
    # API may return a single object or a list/paginated wrapper.
    if isinstance(data, dict) and "results" in data:
        results = data["results"]
        return results[0] if results else None
    return data


def get_transcript(meeting_uuid):
    try:
        return avoma_get(f"{AVOMA_BASE_URL}/transcriptions",
                         params={"meeting_uuid": meeting_uuid})
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return None
        raise


def recording_download_url(recording):
    """Find the best download URL on a recording object (video preferred)."""
    if not recording:
        return None, None
    for key, kind in (("video_url", "video"), ("url", "video"),
                      ("audio_url", "audio")):
        if recording.get(key):
            return recording[key], kind
    return None, None


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
    """Stream an HTTP download directly into S3 via multipart upload.

    Returns the number of bytes uploaded. The video itself is NOT routed
    through Avoma's rate-limited API (the signed URL points at storage),
    so we don't throttle this request.
    """
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        r.raw.decode_content = True  # transparently handle gzip
        size = int(r.headers.get("Content-Length", 0))
        s3.upload_fileobj(
            r.raw, bucket, key,
            ExtraArgs={"StorageClass": storage_class},
        )
    if not size:  # Content-Length missing; read actual size back
        size = s3.head_object(Bucket=bucket, Key=key)["ContentLength"]
    return size


def put_json(s3, bucket, key, obj, storage_class):
    body = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
    s3.put_object(Bucket=bucket, Key=key, Body=body,
                  ContentType="application/json", StorageClass=storage_class)
    return len(body)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="Archive Avoma recordings + transcripts to S3")
    ap.add_argument("--from", dest="from_date", required=True, help="ISO date, e.g. 2024-01-01")
    ap.add_argument("--to", dest="to_date", required=True, help="ISO date, e.g. 2024-12-31")
    ap.add_argument("--dry-run", action="store_true",
                    help="List meetings and sizes, but don't upload")
    args = ap.parse_args()

    missing = [n for n, v in (("AVOMA_API_KEY", AVOMA_API_KEY),
                              ("S3_BUCKET", S3_BUCKET)) if not v]
    if missing and not args.dry_run:
        sys.exit(f"Missing required env vars: {', '.join(missing)}")

    s3 = boto3.client("s3", region_name=AWS_REGION) if not args.dry_run else None

    n_meetings = n_videos = n_transcripts = n_skipped = 0
    video_bytes = transcript_bytes = 0

    for m in iter_meetings(args.from_date, args.to_date):
        uuid = m.get("uuid") or m.get("id")
        if not uuid:
            continue
        n_meetings += 1
        subject = (m.get("subject") or "untitled").strip()
        # YYYY/MM partitioning makes lifecycle rules + browsing sane.
        start = m.get("start_at") or m.get("created") or ""
        ym = start[:7].replace("-", "/") if len(start) >= 7 else "unknown"
        base = f"{S3_PREFIX}/{ym}/{uuid}"
        print(f"[{n_meetings}] {start[:10]}  {subject[:60]}  ({uuid})")

        # ---- transcript ----
        tkey = f"{base}/transcript.json"
        if s3 and s3_object_exists(s3, S3_BUCKET, tkey):
            print("    transcript: already in S3, skip")
            n_skipped += 1
        else:
            transcript = get_transcript(uuid)
            if transcript is None:
                print("    transcript: none available")
            elif args.dry_run:
                print("    transcript: would upload")
            else:
                transcript_bytes += put_json(s3, S3_BUCKET, tkey, transcript,
                                             TRANSCRIPT_STORAGE_CLASS)
                n_transcripts += 1
                print(f"    transcript -> s3://{S3_BUCKET}/{tkey}")

        # ---- recording (video/audio) ----
        recording = get_recording(uuid)
        url, kind = recording_download_url(recording)
        if not url:
            print("    recording: none available")
            continue
        ext = "mp4" if kind == "video" else "mp3"
        vkey = f"{base}/recording.{ext}"
        if s3 and s3_object_exists(s3, S3_BUCKET, vkey):
            print("    recording: already in S3, skip")
            n_skipped += 1
            continue
        if args.dry_run:
            print(f"    recording ({kind}): would stream to s3://{S3_BUCKET}/{vkey}")
            continue
        try:
            n = stream_url_to_s3(s3, url, S3_BUCKET, vkey, VIDEO_STORAGE_CLASS)
            video_bytes += n
            n_videos += 1
            print(f"    recording ({kind}, {n/1e6:.1f} MB) -> s3://{S3_BUCKET}/{vkey}")
        except requests.HTTPError as e:
            # Signed URLs expire; re-fetch once.
            if e.response is not None and e.response.status_code in (401, 403):
                recording = get_recording(uuid)
                url, _ = recording_download_url(recording)
                if url:
                    n = stream_url_to_s3(s3, url, S3_BUCKET, vkey, VIDEO_STORAGE_CLASS)
                    video_bytes += n
                    n_videos += 1
                    print(f"    recording (retried, {n/1e6:.1f} MB)")
            else:
                print(f"    recording ERROR: {e}", file=sys.stderr)

    # ---- summary + cost estimate ----
    gb_video = video_bytes / 1e9
    gb_transcript = transcript_bytes / 1e9
    mo_video = gb_video * PRICE_PER_GB_MONTH.get(VIDEO_STORAGE_CLASS, 0.004)
    mo_transcript = gb_transcript * PRICE_PER_GB_MONTH.get(TRANSCRIPT_STORAGE_CLASS, 0.023)

    print("\n" + "=" * 60)
    print(f"Meetings scanned : {n_meetings}")
    print(f"Videos uploaded  : {n_videos}  ({gb_video:.2f} GB)")
    print(f"Transcripts up   : {n_transcripts}  ({gb_transcript*1000:.1f} MB)")
    print(f"Skipped (exists) : {n_skipped}")
    print("-" * 60)
    print(f"Est. storage/mo  : ${mo_video + mo_transcript:.2f}")
    print(f"  video  ({VIDEO_STORAGE_CLASS:<12}) : ${mo_video:.2f}/mo")
    print(f"  transcripts     : ${mo_transcript:.4f}/mo")
    print("  (one-time PUT requests: ~$0.005 per 1,000 uploads)")
    print("=" * 60)


if __name__ == "__main__":
    main()
