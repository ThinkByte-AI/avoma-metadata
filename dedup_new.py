#!/usr/bin/env python3
"""
Dedup the NEW batch of member CSVs (keys2.txt) by meeting uuid, then subtract
any uuid already present in the batch-1 manifest (meetings_deduped.csv).

Writes meetings_deduped2.csv = the NET-NEW unique meetings introduced by the
new accounts. Same columns as meetings_deduped.csv so pull_deduped_to_s3.py can
archive it directly (MANIFEST=meetings_deduped2.csv KEYS_FILE=keys2.txt).
"""
import csv, os

NEW_KEYS = os.environ.get("KEYS_FILE", "keys2.txt")
PRIOR = os.environ.get("PRIOR_MANIFEST", "meetings_deduped.csv")
OUT = os.environ.get("OUT", "meetings_deduped2.csv")

names = [l.split()[0] for l in open(NEW_KEYS, encoding="utf-8") if l.strip()]
files = [f"meetings_{n}.csv" for n in names if os.path.exists(f"meetings_{n}.csv")]
print(f"New-batch files: {len(files)}/{len(names)} -> {names}")

# 1) dedup within the new batch
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

# 2) subtract uuids already in the prior (batch-1) manifest
prior = set()
if os.path.exists(PRIOR):
    with open(PRIOR, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("uuid"):
                prior.add(r["uuid"])
print(f"Prior manifest uuids: {len(prior):,}")

net_new = {u: m for u, m in uniq.items() if u not in prior}
overlap = len(uniq) - len(net_new)

# 3) write net-new manifest
with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["uuid", "subject", "start", "duration_min", "video_ready",
                "transcript_ready", "recording_uuid", "transcription_uuid",
                "owner_key", "n_accounts"])
    for u, m in net_new.items():
        w.writerow([u, m["subject"], m["start"], round(m["dur"], 1), m["vid"], m["txt"],
                    m["rec"], m["tr"], sorted(m["owners"])[0], len(m["owners"])])

nv = sum(1 for m in net_new.values() if m["vid"])
nt = sum(1 for m in net_new.values() if m["txt"])
print("=" * 56)
print(f"  Raw new-batch rows     : {total_rows:,}")
print(f"  Unique in new batch    : {len(uniq):,}")
print(f"  Already in batch-1     : {overlap:,}  (skipped)")
print(f"  NET-NEW unique meetings: {len(net_new):,}  -> {OUT}")
print(f"    with video+audio     : {nv:,}")
print(f"    with transcript      : {nt:,}")
print("=" * 56)
