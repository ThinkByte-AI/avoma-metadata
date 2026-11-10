#!/usr/bin/env python3
"""Measure actual MB/hour on the DEDUPED recorded set (gentle, single-thread).
Reads meetings_deduped.csv, samples N video recordings evenly, uses each row's
owner_key to fetch the recording, reads Content-Length without downloading."""
import csv, os, sys, time, requests

SAMPLE = int(os.environ.get("SAMPLE", "50"))
THROTTLE = 60.0 / 35  # gentle: ~35/min single thread

keymap = {l.split()[0]: l.split()[1] for l in open("keys.txt", encoding="utf-8") if l.strip()}

rec = []
with open("meetings_deduped.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        if r["video_ready"] == "True" and r["recording_uuid"]:
            rec.append(r)
total_hours = sum(float(r["duration_min"] or 0) for r in rec) / 60.0
print(f"{len(rec)} deduped recordings, {total_hours:.0f} recorded hours; sampling {SAMPLE}", file=sys.stderr)

step = max(1, len(rec) // SAMPLE)
sample = rec[::step][:SAMPLE]

tot_b = tot_min = 0.0
n = 0
for i, r in enumerate(sample, 1):
    key = keymap.get(r["owner_key"])
    if not key:
        continue
    h = {"Authorization": "Bearer " + key}
    time.sleep(THROTTLE)
    try:
        rj = requests.get(f"https://api.avoma.com/v1/recordings/{r['recording_uuid']}",
                          headers=h, timeout=30).json()
        url = rj.get("video_url") or rj.get("url")
        mins = (float(rj["duration"]) / 60.0) if rj.get("duration") else float(r["duration_min"] or 0)
        if not url or mins <= 0:
            continue
        with requests.get(url, stream=True, timeout=60) as resp:
            b = int(resp.headers.get("Content-Length", 0))
        if not b:
            continue
        tot_b += b; tot_min += mins; n += 1
        if i % 10 == 0:
            print(f"  {i}/{SAMPLE} sampled... running {(tot_b/1e6)/(tot_min/60):.0f} MB/hr", file=sys.stderr)
    except Exception as e:
        print(f"  {i} err {e}", file=sys.stderr)

mbph = (tot_b / 1e6) / (tot_min / 60.0)
gb = total_hours * mbph / 1000.0
PRICE = {"GLACIER_IR": 0.004, "STANDARD_IA": 0.0125, "STANDARD": 0.023, "DEEP_ARCHIVE": 0.00099}
print("\n" + "=" * 56)
print(f"  Samples measured     : {n}")
print(f"  MEASURED bitrate      : {mbph:,.0f} MB/hour")
print(f"  Deduped recorded hrs : {total_hours:,.0f}")
print(f"  TOTAL video size     : {gb:,.0f} GB ({gb/1000:.2f} TB)")
print("-" * 56)
for c in ("GLACIER_IR", "STANDARD_IA", "STANDARD", "DEEP_ARCHIVE"):
    print(f"  {c:<14} ${gb*PRICE[c]:,.2f}/mo")
print("=" * 56)
