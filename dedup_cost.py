#!/usr/bin/env python3
"""
Dedup meetings across all member CSVs by uuid, then report unique recorded
hours, storage, and S3 cost. Runs over whatever meetings_<name>.csv exist.

MB/hour defaults to 85 (measured: Harsha 89, charan 80). Override via env.
"""
import csv, glob, os

MB_PER_HOUR = float(os.environ.get("MB_PER_HOUR", "85"))
PRICE = {"GLACIER_IR": 0.004, "STANDARD_IA": 0.0125, "STANDARD": 0.023,
         "DEEP_ARCHIVE": 0.00099}

# read exactly the 10 member files named in keys.txt (avoid stale extras)
names = [l.split()[0] for l in open("keys.txt", encoding="utf-8") if l.strip()]
files = [f"meetings_{n}.csv" for n in names if os.path.exists(f"meetings_{n}.csv")]
print(f"Reading {len(files)} member files: {names}")

uniq = {}
total_rows = 0
for path in files:
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            total_rows += 1
            u = r.get("uuid")
            if not u:
                continue
            vid = r.get("video_ready") == "True"
            txt = r.get("transcript_ready") == "True"
            if u not in uniq:
                uniq[u] = {"subject": r.get("subject", ""), "start": r.get("start", ""),
                           "dur": float(r.get("duration_min") or 0), "vid": vid, "txt": txt,
                           "rec": r.get("recording_uuid", ""), "tr": r.get("transcription_uuid", ""),
                           "owners": {r.get("owner", "")}}
            else:
                e = uniq[u]
                e["vid"] = e["vid"] or vid
                e["txt"] = e["txt"] or txt
                e["owners"].add(r.get("owner", ""))
                if not e["rec"] and r.get("recording_uuid"):
                    e["rec"] = r["recording_uuid"]

n_uniq = len(uniq)
rec = [m for m in uniq.values() if m["vid"]]
n_rec = len(rec)
rec_hours = sum(m["dur"] for m in rec) / 60.0
n_txt = sum(1 for m in uniq.values() if m["txt"])
dup = total_rows / n_uniq if n_uniq else 1

# write deduped manifest (used later by the downloader)
with open("meetings_deduped.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["uuid", "subject", "start", "duration_min", "video_ready",
                "transcript_ready", "recording_uuid", "transcription_uuid",
                "owner_key", "n_accounts"])
    for u, m in uniq.items():
        w.writerow([u, m["subject"], m["start"], round(m["dur"], 1), m["vid"], m["txt"],
                    m["rec"], m["tr"], sorted(m["owners"])[0], len(m["owners"])])

gb = rec_hours * MB_PER_HOUR / 1000.0
print("\n" + "=" * 60)
print(f"  Account files read        : {len(files)}/10")
print(f"  Raw meeting-records       : {total_rows:,}")
print(f"  UNIQUE meetings (deduped) : {n_uniq:,}   (dup factor {dup:.2f}x)")
print(f"  Unique with VIDEO         : {n_rec:,}")
print(f"  Unique with transcript    : {n_txt:,}")
print(f"  Unique recorded hours     : {rec_hours:,.1f}")
print(f"  Est. video size @ {MB_PER_HOUR:.0f} MB/hr : {gb:,.0f} GB ({gb/1000:.2f} TB)")
print("-" * 60)
for c in ("GLACIER_IR", "STANDARD_IA", "STANDARD", "DEEP_ARCHIVE"):
    print(f"  {c:<14} ${gb*PRICE[c]:,.2f}/mo")
print("=" * 60)
