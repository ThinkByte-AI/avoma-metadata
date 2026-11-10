#!/usr/bin/env python3
"""
Extract the Sigma (SigmaInfo) client meetings from the pulled Avoma notes.

Filters data/notes/worklist.csv to meetings whose subject mentions "sigma",
downloads each meeting's notes.json + notes.md from S3 into clients/sigma/meetings/,
builds one combined chronological clients/sigma/sigma_notes.md, and writes a
clients/sigma/sigma_meetings.csv index.

Usage (run from the repo root):
    python clients/sigma/extract_sigma.py
"""
import csv
import os
import re

import boto3

BUCKET = os.environ.get("S3_BUCKET", "avoma-archive-growthbyte")
REGION = os.environ.get("AWS_REGION", "ap-south-1")
PREFIX = os.environ.get("S3_PREFIX", "avoma").strip("/")
WORKLIST = os.path.join("data", "notes", "worklist.csv")
CLIENT_DIR = os.path.join("clients", "sigma")
OUT = os.path.join(CLIENT_DIR, "meetings")
COMBINED_MD = os.path.join(CLIENT_DIR, "sigma_notes.md")
INDEX_CSV = os.path.join(CLIENT_DIR, "sigma_meetings.csv")
TERM = re.compile(r"sigma", re.I)


def load_dotenv(path=".env"):
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def safe(s, n=45):
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")
    return s[:n]


def s3_base(uuid, start):
    ym = start[:7].replace("-", "/") if len(start) >= 7 else "unknown"
    return f"{PREFIX}/{ym}/{uuid}"


def main():
    load_dotenv()
    s3 = boto3.client("s3", region_name=REGION)
    os.makedirs(OUT, exist_ok=True)

    rows = []
    with open(WORKLIST, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if TERM.search(r.get("subject", "")):
                rows.append(r)
    rows.sort(key=lambda r: r["start"])
    print(f"{len(rows)} Sigma meetings found")

    combined = ["# Sigma (SigmaInfo) — All Meeting Summaries",
                f"_{len(rows)} meetings, {rows[0]['start'][:10]} → "
                f"{rows[-1]['start'][:10]}_", ""]
    index_rows = []
    n_ok = n_empty = 0

    for r in rows:
        uuid, start, subject = r["uuid"], r["start"], r["subject"]
        base = s3_base(uuid, start)
        stem = f"{start[:10]}_{safe(subject)}_{uuid[:8]}"
        md_text = ""
        for ext, ctype in (("json", None), ("md", None)):
            try:
                body = s3.get_object(Bucket=BUCKET,
                                     Key=f"{base}/notes.{ext}")["Body"].read()
                with open(os.path.join(OUT, f"{stem}.{ext}"), "wb") as out:
                    out.write(body)
                if ext == "md":
                    md_text = body.decode("utf-8", "replace")
            except s3.exceptions.NoSuchKey:
                print(f"  MISSING notes.{ext} for {uuid}")

        has = bool(md_text and "(no AI notes generated" not in md_text)
        n_ok += has
        n_empty += (not has)
        index_rows.append([start[:16], subject, uuid,
                           r.get("owners", ""), "yes" if has else "empty",
                           f"s3://{BUCKET}/{base}/notes.md"])

        combined.append("\n---\n")
        combined.append(f"## {start[:10]} — {subject}")
        combined.append(f"_attendees: {r.get('owners','').replace('|', ', ')}_\n")
        # drop the per-note duplicate H1 title; keep the body
        body_md = re.sub(r"^# .*\n(_.*_\n)?", "", md_text).strip()
        combined.append(body_md if body_md else "_(no AI notes generated)_")

    with open(COMBINED_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(combined) + "\n")

    with open(INDEX_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["start", "subject", "uuid", "attendees", "notes", "s3_path"])
        w.writerows(index_rows)

    print(f"Downloaded into {OUT}/ : {len(rows)} meetings "
          f"({n_ok} with notes, {n_empty} empty)")
    print(f"Combined doc : {COMBINED_MD}")
    print(f"Index        : {INDEX_CSV}")


if __name__ == "__main__":
    main()
