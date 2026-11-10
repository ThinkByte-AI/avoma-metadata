#!/usr/bin/env python3
"""Measure ACTUAL video MB/hour by sampling real recordings' byte sizes.

Reads meetings_2yr.csv, samples N recorded meetings evenly across the period,
calls /recordings to get each signed video_url, then reads the file's
Content-Length from a streaming GET WITHOUT downloading the body.
Extrapolates to the full recorded-hours total for an exact cost.
"""
import csv, os, sys, time, requests

KEY = os.environ["AVOMA_API_KEY"]
H = {"Authorization": "Bearer " + KEY}
SAMPLE = int(os.environ.get("SAMPLE", "40"))
CSV_FILE = os.environ.get("CSV_FILE", "meetings_2yr.csv")
TOTAL_RECORDED_HOURS = float(os.environ.get("TOTAL_RECORDED_HOURS", "1576.5"))
THROTTLE = 60.0 / 55

PRICE = {"STANDARD": 0.023, "STANDARD_IA": 0.0125, "GLACIER_IR": 0.004,
         "GLACIER": 0.0036, "DEEP_ARCHIVE": 0.00099}

# load recorded meetings
recorded = []
with open(CSV_FILE, encoding="utf-8") as f:
    for r in csv.DictReader(f):
        if r["video_ready"] == "True" and r["recording_uuid"]:
            recorded.append(r)
print(f"{len(recorded)} recorded meetings in CSV; sampling {SAMPLE} evenly", file=sys.stderr)

# even sample across the list (chronological)
step = max(1, len(recorded) // SAMPLE)
sample = recorded[::step][:SAMPLE]

def content_length(url):
    # signed S3 URL is signed for GET; stream and read header, don't pull body
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        n = r.headers.get("Content-Length")
        return int(n) if n else None

rows = []
tot_bytes = tot_min = 0.0
for i, m in enumerate(sample, 1):
    time.sleep(THROTTLE)
    try:
        rec = requests.get(f"https://api.avoma.com/v1/recordings/{m['recording_uuid']}",
                           headers=H, timeout=30).json()
    except Exception as e:
        print(f"  {i:>3} rec-api ERR {e}", file=sys.stderr); continue
    url = rec.get("video_url") or rec.get("url")
    dur_s = rec.get("duration")  # actual recording duration if present
    mins = (float(dur_s) / 60.0) if dur_s else float(m["duration_min"] or 0)
    if not url or mins <= 0:
        print(f"  {i:>3} skip (no url/dur)", file=sys.stderr); continue
    try:
        b = content_length(url)
    except Exception as e:
        print(f"  {i:>3} size ERR {e}", file=sys.stderr); continue
    if not b:
        continue
    tot_bytes += b; tot_min += mins
    rows.append((mins, b))
    print(f"  {i:>3}/{SAMPLE}  {b/1e6:7.1f} MB  {mins:5.1f} min  "
          f"{(b/1e6)/(mins/60):6.0f} MB/hr  {m['start'][:10]}", file=sys.stderr)

if not rows:
    sys.exit("No samples measured.")

mb_per_hour = (tot_bytes / 1e6) / (tot_min / 60.0)
proj_gb = TOTAL_RECORDED_HOURS * mb_per_hour / 1000.0

print("\n" + "=" * 60)
print(f"  Samples measured     : {len(rows)}")
print(f"  Measured total       : {tot_bytes/1e9:.2f} GB over {tot_min/60:.1f} hours")
print(f"  ACTUAL avg bitrate    : {mb_per_hour:,.0f} MB/hour")
print("-" * 60)
print(f"  Projected to ALL {TOTAL_RECORDED_HOURS:,.0f} recorded hours:")
print(f"  Total video size     : {proj_gb:,.0f} GB  ({proj_gb/1000:.2f} TB)")
print("-" * 60)
for cls in ("GLACIER_IR", "STANDARD_IA", "STANDARD", "DEEP_ARCHIVE"):
    print(f"  {cls:<14} ${proj_gb*PRICE[cls]:,.2f}/mo")
print("=" * 60)
