#!/usr/bin/env python3
"""
Scan member accounts for recorded-meeting metadata, GENTLY and RESUMABLY.

Lessons learned: 10 parallel scanners (~350 req/min from one IP for minutes)
tripped Avoma's edge WAF -> IP-wide 403 block. So:
  * low concurrency (MAX_CONCURRENCY, default 3 accounts at once)
  * modest per-key rate (PER_KEY_RPM, default 40/min)
  * 403/HTML-WAF + 429 + 5xx all get exponential backoff and retry
  * RESUMABLE: an account is "done" iff meetings_<name>.csv exists; reruns skip it
  * partial pages are checkpointed to meetings_<name>.csv.part so a crash
    doesn't throw away progress

Run it repeatedly until all 10 CSVs exist; then run dedup_cost.py.
"""
import csv, os, sys, time, threading, queue
from datetime import datetime
import requests

FROM_DATE = "2023-12-06"   # 2.5 years
TO_DATE   = "2026-06-06"
MAX_CONCURRENCY = int(os.environ.get("MAX_CONCURRENCY", "3"))
PER_KEY_RPM     = float(os.environ.get("PER_KEY_RPM", "40"))
THROTTLE = 60.0 / PER_KEY_RPM

KEYS_FILE = os.environ.get("KEYS_FILE", "keys.txt")
keys = [l.split() for l in open(KEYS_FILE, encoding="utf-8") if l.strip()]
lock = threading.Lock()
progress = {}

FIELDS = ["uuid", "subject", "start", "duration_min", "video_ready",
          "transcript_ready", "recording_uuid", "transcription_uuid", "owner"]


def parse_dt(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None
    except ValueError:
        return None


def duration_minutes(m):
    d = m.get("duration")
    if d is not None:
        try:
            v = float(d)
            return v / 60.0 if v > 180 else v
        except (TypeError, ValueError):
            pass
    a, b = parse_dt(m.get("start_at")), parse_dt(m.get("end_at"))
    return max(0.0, (b - a).total_seconds() / 60.0) if a and b else 0.0


def has_video(m):
    return (m.get("video_ready") is True or
            m.get("recording_state") in ("done", "completed", "ready", "available"))


def get(url, headers, params, retries=8):
    last = "no response"
    for i in range(retries):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=60)
        except requests.RequestException as e:
            last = f"network error: {e}"
            time.sleep(min(5 * (i + 1), 60)); continue
        if r.status_code == 200:
            return r.json()
        last = f"status {r.status_code}"
        # 403 here is usually the IP WAF block -> long backoff; also 429/5xx
        wait = min(15 * (i + 1), 120) if r.status_code == 403 else min(2 ** i, 30)
        wait = int(r.headers.get("Retry-After", wait))
        time.sleep(wait)
    raise RuntimeError(f"give up {url} ({last})")


def scan_one(name, key):
    out = f"meetings_{name}.csv"
    if os.path.exists(out):
        with lock:
            progress[name] = "done(cached)"
        return
    h = {"Authorization": "Bearer " + key}
    url = "https://api.avoma.com/v1/meetings"
    params = {"from_date": FROM_DATE, "to_date": TO_DATE, "page_size": 100}
    rows, pages, last = [], 0, 0.0
    while url:
        dt = time.monotonic() - last
        if dt < THROTTLE:
            time.sleep(THROTTLE - dt)
        last = time.monotonic()
        data = get(url, h, params)
        pages += 1
        for m in data.get("results", []):
            rows.append({
                "uuid": m.get("uuid"),
                "subject": (m.get("subject") or "").strip().replace("\n", " "),
                "start": m.get("start_at") or "",
                "duration_min": round(duration_minutes(m), 1),
                "video_ready": has_video(m),
                "transcript_ready": bool(m.get("transcript_ready") or m.get("transcription_uuid")),
                "recording_uuid": m.get("recording_uuid") or "",
                "transcription_uuid": m.get("transcription_uuid") or "",
                "owner": name,
            })
        with lock:
            progress[name] = f"{len(rows)} ({pages}p)"
        url = data.get("next")
        params = None
        if pages % 50 == 0:  # checkpoint
            _write(out + ".part", rows)
    _write(out, rows)
    if os.path.exists(out + ".part"):
        os.remove(out + ".part")
    with lock:
        progress[name] = f"DONE {len(rows)}"
    print(f"[done] {name}: {len(rows)} meetings", file=sys.stderr)


def _write(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def worker(q):
    while True:
        try:
            name, key = q.get_nowait()
        except queue.Empty:
            return
        try:
            scan_one(name, key)
        except Exception as e:
            with lock:
                progress[name] = f"FAILED {e}"
            print(f"[fail] {name}: {e}", file=sys.stderr)
        finally:
            q.task_done()


def main():
    q = queue.Queue()
    for n, k in keys:
        q.put((n, k))
    workers = [threading.Thread(target=worker, args=(q,), daemon=True)
               for _ in range(MAX_CONCURRENCY)]
    for w in workers:
        w.start()
    while any(w.is_alive() for w in workers):
        time.sleep(20)
        with lock:
            print("  " + " | ".join(f"{n}:{progress.get(n,'-')}" for n, _ in keys),
                  file=sys.stderr)
    done = [n for n, _ in keys if os.path.exists(f"meetings_{n}.csv")]
    print(f"\nComplete accounts: {len(done)}/{len(keys)} -> {done}", file=sys.stderr)
    if len(done) < len(keys):
        print("Re-run this script to resume the missing accounts.", file=sys.stderr)


if __name__ == "__main__":
    main()
