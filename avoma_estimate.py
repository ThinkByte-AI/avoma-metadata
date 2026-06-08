#!/usr/bin/env python3
"""
Avoma metadata-only estimator — pull every meeting's metadata (NO downloads),
compute total recorded hours, and project S3 storage size + cost.

This is the cheap/fast first step before any S3 sync:
  1. Fetch all meetings (cursor-paginated) -> metadata only
  2. Compute duration per meeting from start/end times (or a `duration` field)
  3. Sum total hours, write a CSV, and project storage GB + monthly $ at
     several video-bitrate and storage-class assumptions.

Needs only AVOMA_API_KEY. No boto3, no AWS, nothing downloaded.

Usage:
    pip install requests
    $env:AVOMA_API_KEY="..."           # PowerShell
    python avoma_estimate.py --from 2023-01-01 --to 2026-06-06
    python avoma_estimate.py --from 2023-01-01 --to 2026-06-06 --csv meetings.csv
"""

import argparse
import csv
import os
import sys
import time
from datetime import datetime

import requests

AVOMA_API_KEY = os.environ.get("AVOMA_API_KEY", "")
AVOMA_BASE_URL = os.environ.get("AVOMA_BASE_URL", "https://api.avoma.com/v1")
MIN_SECONDS_BETWEEN_CALLS = 60.0 / float(os.environ.get("AVOMA_RPM", "55"))

# Assumed video size per hour of meeting, for three quality tiers (MB/hour).
# Avoma recordings vary with resolution/screen-share; tweak if you learn yours.
MB_PER_HOUR = {"low": 150, "medium": 300, "high": 500}

# $/GB/month, us-east-1 list prices.
PRICE_PER_GB_MONTH = {
    "STANDARD": 0.023,
    "STANDARD_IA": 0.0125,
    "GLACIER_IR": 0.004,
    "GLACIER": 0.0036,
    "DEEP_ARCHIVE": 0.00099,
}

session = requests.Session()
session.headers.update({"Authorization": f"Bearer {AVOMA_API_KEY}"})
_last = [0.0]


def _throttle():
    elapsed = time.monotonic() - _last[0]
    if elapsed < MIN_SECONDS_BETWEEN_CALLS:
        time.sleep(MIN_SECONDS_BETWEEN_CALLS - elapsed)
    _last[0] = time.monotonic()


def avoma_get(url, params=None, max_retries=5):
    for attempt in range(max_retries):
        _throttle()
        r = session.get(url, params=params, timeout=60)
        if r.status_code == 429 or r.status_code >= 500:
            wait = int(r.headers.get("Retry-After", min(2 ** attempt, 30)))
            print(f"  [{r.status_code}] backing off {wait}s...", file=sys.stderr)
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"Giving up on {url}")


def iter_meetings(from_date, to_date, page_size=100):
    url = f"{AVOMA_BASE_URL}/meetings"
    params = {"from_date": from_date, "to_date": to_date, "page_size": page_size}
    page = 0
    while url:
        page += 1
        data = avoma_get(url, params=params)
        results = data.get("results", data if isinstance(data, list) else [])
        print(f"  page {page}: {len(results)} meetings", file=sys.stderr)
        for m in results:
            yield m
        url = data.get("next") if isinstance(data, dict) else None
        params = None


def _get(d, *keys):
    for k in keys:
        if d.get(k) not in (None, ""):
            return d[k]
    return None


def parse_dt(s):
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
    return None


def duration_minutes(m):
    """Prefer an explicit duration field (seconds); else end - start."""
    dur = _get(m, "duration", "duration_seconds", "audio_duration")
    if dur is not None:
        try:
            val = float(dur)
            # Avoma's `duration` is in seconds.
            return val / 60.0 if val > 180 else val
        except (TypeError, ValueError):
            pass
    start = parse_dt(_get(m, "start_at", "start_time", "start", "scheduled_start"))
    end = parse_dt(_get(m, "end_at", "end_time", "end", "scheduled_end"))
    if start and end:
        return max(0.0, (end - start).total_seconds() / 60.0)
    return 0.0


def has_video(m):
    """True if the meeting actually has a recorded VIDEO ready to download."""
    if m.get("video_ready") is True:
        return True
    if m.get("recording_state") in ("done", "completed", "ready", "available"):
        return True
    return False


def has_audio(m):
    return bool(m.get("audio_ready") or m.get("recording_uuid"))


def has_transcript(m):
    return bool(m.get("transcript_ready") or m.get("transcription_uuid"))


def fmt_money(x):
    return f"${x:,.2f}" if x >= 1 else f"${x:.4f}"


def main():
    ap = argparse.ArgumentParser(description="Estimate Avoma -> S3 storage from metadata only")
    ap.add_argument("--from", dest="from_date", required=True, help="ISO date e.g. 2023-01-01")
    ap.add_argument("--to", dest="to_date", required=True, help="ISO date e.g. 2026-06-06")
    ap.add_argument("--csv", default="meetings_metadata.csv", help="output CSV path")
    args = ap.parse_args()

    if not AVOMA_API_KEY:
        sys.exit("Set AVOMA_API_KEY first.")

    rows = []
    total_min = 0.0          # all meetings (scheduled time)
    rec_min = 0.0            # only meetings with video ready
    n = n_video = n_audio = n_transcript = 0

    print("Fetching meeting metadata (no downloads)...", file=sys.stderr)
    for m in iter_meetings(args.from_date, args.to_date):
        mid = _get(m, "uuid", "id")
        title = (_get(m, "subject", "title") or "").strip()
        start = _get(m, "start_at", "start_time", "start") or ""
        end = _get(m, "end_at", "end_time", "end") or ""
        mins = duration_minutes(m)
        vid, aud, txt = has_video(m), has_audio(m), has_transcript(m)
        parts = m.get("attendees") or m.get("participants") or []
        n += 1
        total_min += mins
        if vid:
            n_video += 1
            rec_min += mins
        if aud:
            n_audio += 1
        if txt:
            n_transcript += 1
        rows.append({
            "id": mid, "title": title, "start": start, "end": end,
            "duration_min": round(mins, 1),
            "video_ready": vid, "audio_ready": aud, "transcript_ready": txt,
            "recording_uuid": m.get("recording_uuid") or "",
            "transcription_uuid": m.get("transcription_uuid") or "",
            "recording_state": m.get("recording_state") or "",
            "participants": len(parts) if isinstance(parts, list) else "",
        })

    # write CSV
    with open(args.csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else
                           ["id", "title", "start", "end", "duration_min",
                            "has_recording", "participants"])
        w.writeheader()
        w.writerows(rows)

    total_hours = total_min / 60.0
    rec_hours = rec_min / 60.0
    avg_min = (rec_min / n_video) if n_video else 0

    print("\n" + "=" * 66)
    print(f"  Meetings on calendar      : {n:,}")
    print(f"  -> with VIDEO recorded    : {n_video:,}   <-- these drive storage cost")
    print(f"  -> with audio/recording   : {n_audio:,}")
    print(f"  -> with transcript        : {n_transcript:,}")
    print(f"  Recorded video time       : {rec_min:,.0f} min  =  {rec_hours:,.1f} hours")
    print(f"  Avg recorded meeting len  : {avg_min:,.1f} min")
    print(f"  Metadata CSV              : {args.csv}")
    print("=" * 66)

    # Storage projection is based on RECORDED hours only.
    total_hours = rec_hours
    print("\n  PROJECTED VIDEO STORAGE (recorded meetings only; transcripts <1%):\n")
    print(f"  {'Quality':<10}{'MB/hour':>9}{'Total size':>14}"
          + "".join(f"{c:>13}" for c in ("GLACIER_IR", "STD_IA", "STANDARD")))
    print(f"  {'':<10}{'':>9}{'':>14}{'$/mo':>13}{'$/mo':>13}{'$/mo':>13}")
    print("  " + "-" * 62)
    for tier, mbph in MB_PER_HOUR.items():
        gb = total_hours * mbph / 1000.0
        ir = gb * PRICE_PER_GB_MONTH["GLACIER_IR"]
        ia = gb * PRICE_PER_GB_MONTH["STANDARD_IA"]
        std = gb * PRICE_PER_GB_MONTH["STANDARD"]
        size = f"{gb/1000:.2f} TB" if gb >= 1000 else f"{gb:.1f} GB"
        print(f"  {tier:<10}{mbph:>9}{size:>14}"
              f"{fmt_money(ir):>13}{fmt_money(ia):>13}{fmt_money(std):>13}")
    print("  " + "-" * 62)
    print("  Notes: upload INTO S3 is free; PUTs ~$0.005/1,000 files (one-time).")
    print("         'medium' (~300 MB/hr) is a reasonable default for Avoma video.")
    print("         Reading back later: ~$0.03/GB retrieval + $0.09/GB egress out of AWS.")
    print("=" * 66)


if __name__ == "__main__":
    main()
