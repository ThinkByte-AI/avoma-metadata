#!/usr/bin/env python3
"""Probe which Avoma endpoint returns AI notes / summary, and confirm the
new key file's auth format. Read-only, a handful of GETs, gentle.

Picks one person (default Harsha), finds one transcript-ready meeting from their
CSV, and tries candidate endpoints. Prints status + a short body preview so we
can see the real schema before building the bulk puller.

Usage (run from the repo root):
    python notes-puller/probe_notes.py
"""
import csv, json, os, sys, time
import requests

KEYS_FILE = os.environ.get("KEYS_FILE", "avoma api key.txt")
PERSON    = os.environ.get("PROBE_PERSON", "Harsha")
BASE      = "https://api.avoma.com/v1"


def load_keys(path):
    """File lines look like 'Harsha-n70juqelin:secret'. Name is everything
    before the first '-'; the bearer token is everything after it
    ('<keyid>:<secret>')."""
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            name, _, token = line.partition("-")
            out[name.strip()] = token.strip()
    return out


def find_transcript_uuid(person):
    path = os.path.join("data", "metadata", f"meetings_{person}.csv")
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("transcript_ready") == "True":
                return r["uuid"], r.get("subject", ""), r.get("transcription_uuid", "")
    return None, None, None


def preview(resp):
    body = resp.text
    try:
        j = resp.json()
        body = json.dumps(j, ensure_ascii=False)[:600]
    except Exception:
        body = body[:300]
    return body


def main():
    keys = load_keys(KEYS_FILE)
    if PERSON not in keys:
        sys.exit(f"{PERSON} not in {KEYS_FILE}; have: {list(keys)}")
    token = keys[PERSON]
    uuid, subject, tx_uuid = find_transcript_uuid(PERSON)
    if not uuid:
        sys.exit(f"No transcript-ready meeting found for {PERSON}")
    print(f"Person   : {PERSON}  (token id={token.split(':')[0]})")
    print(f"Meeting  : {uuid}  '{subject[:50]}'  tx_uuid={tx_uuid}\n")

    h = {"Authorization": "Bearer " + token}
    candidates = [
        ("GET", f"{BASE}/transcriptions", {"meeting_uuid": uuid}),       # known-good auth check
        ("GET", f"{BASE}/meetings/{uuid}", None),                        # detail may embed notes
        ("GET", f"{BASE}/smart_categories", {"meeting_uuid": uuid}),
        ("GET", f"{BASE}/notes", {"meeting_uuid": uuid}),
        ("GET", f"{BASE}/smart_notes", {"meeting_uuid": uuid}),
        ("GET", f"{BASE}/meetings/{uuid}/notes", None),
        ("GET", f"{BASE}/meeting_sentiments", {"meeting_uuid": uuid}),
    ]
    for method, url, params in candidates:
        time.sleep(1.5)  # gentle
        try:
            r = requests.get(url, headers=h, params=params, timeout=30)
            tag = url.replace(BASE, "")
            print(f"[{r.status_code}] {tag}  params={params}")
            if r.status_code == 200:
                print("      -> " + preview(r) + "\n")
            elif r.status_code in (400, 404):
                print("      -> " + preview(r)[:160] + "\n")
        except requests.RequestException as e:
            print(f"[ERR] {url}: {e}")


if __name__ == "__main__":
    main()
