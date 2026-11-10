# Avoma → S3 archiver

Pulls your Avoma **meeting recordings (video/audio)** and **transcripts** and archives them to an S3 bucket. Resumable, rate-limit aware, streams video straight from Avoma to S3 (nothing big lands on your disk).

> Run every command below **from the repo root** (where `.env`, `requirements.txt` and the key files live).

| Script | What it does |
| --- | --- |
| `avoma_to_s3.py` | Archive recordings + transcripts for a date range to S3 (the main tool) |
| `scan_all.py` | Scan each member account for recorded-meeting metadata → `meetings_<name>.csv` |
| `dedup_cost.py`, `dedup_new.py` | De-duplicate meetings across accounts → `meetings_deduped*.csv`, with a cost estimate |
| `pull_deduped_to_s3.py` | Archive the de-duplicated set to S3, one meeting at a time (resumable) |
| `avoma_estimate.py` | Metadata-only storage and cost estimate (no downloads, no AWS) |
| `probe_sizes.py`, `probe_deduped.py` | Sample real recordings to measure MB per hour |

## Setup

1. **Install deps**
   ```powershell
   pip install -r requirements.txt
   ```

2. **Get your Avoma API key** — Avoma → Settings → Organization → Developer → *Add API Key*. (Help: https://help.avoma.com/api-integration-for-avoma)

3. **Create an S3 bucket** (once):
   ```powershell
   aws s3 mb s3://my-avoma-archive --region us-east-1
   ```

4. **Configure** — copy `.env.example` and fill it in, then load it:
   ```powershell
   # PowerShell: load .env into the session
   Get-Content .env | ForEach-Object { if ($_ -match '^\s*([^#][^=]+)=(.*)$') { $env:($matches[1].Trim()) = $matches[2].Trim() } }
   ```

5. **Dry run first** (lists meetings, uploads nothing):
   ```powershell
   python archiver/avoma_to_s3.py --from 2024-01-01 --to 2024-12-31 --dry-run
   ```

6. **Run for real:**
   ```powershell
   python archiver/avoma_to_s3.py --from 2024-01-01 --to 2024-12-31
   ```

It's safe to re-run — anything already in S3 is skipped, so you can stop/resume or widen the date range anytime.

## How it works / layout in S3

```
s3://my-avoma-archive/avoma/<YYYY>/<MM>/<meeting-uuid>/recording.mp4   (Glacier Instant Retrieval)
s3://my-avoma-archive/avoma/<YYYY>/<MM>/<meeting-uuid>/transcript.json (Standard)
```

- **Meetings** are listed via `GET /v1/meetings?from_date=&to_date=` (cursor-paginated).
- **Recordings** via `GET /v1/recordings?meeting_uuid=…` — returns a short-lived signed URL that the script streams into S3 (re-fetched automatically if it expires mid-run).
- **Transcripts** via `GET /v1/transcriptions?meeting_uuid=…` — saved as JSON.
- Auth header: `Authorization: Bearer <AVOMA_API_KEY>`. Base URL `https://api.avoma.com/v1`.
- Throttled to ~55 req/min (Avoma's limit is 60/min) with backoff on 429/5xx.

> If your endpoint field names differ slightly (Avoma occasionally returns `url` vs `video_url`, or wraps results in `results`), the script already handles the common variants. Run `--dry-run` once and check the output; the full live schema is at https://dev.avoma.com.

---

## 💰 What does S3 actually cost?

**Short answer for your case (~5,000 meetings, ~1.25 TB, occasional access):**
**≈ $5 / month** for storage, plus a **one-time ~$0.03** for the uploads. That's it.

### Why so cheap

| Cost item | Rate (us-east-1) | Your case | Cost |
|---|---|---|---|
| **Upload INTO S3** (data transfer in) | **$0.00** | 1.25 TB | **$0.00** — ingress is always free |
| **PUT requests** (one per file) | $0.005 / 1,000 | ~10,000 uploads | **~$0.05 one-time** |
| **Storage — video** (Glacier Instant Retrieval) | $0.004 / GB / mo | ~1.25 TB | **~$5.00 / mo** |
| **Storage — transcripts** (Standard) | $0.023 / GB / mo | ~0.5 GB | **~$0.01 / mo** |
| **Egress** from Avoma → you | Avoma pays it | — | **$0.00 to you** |

You only ever pay AWS for **storage** + tiny request fees. Downloading the videos *out of Avoma* costs you nothing (Avoma serves them); uploading *into* S3 is free.

### Storage class trade-off (1.25 TB of video)

| Class | $/GB/mo | **Your ~1.25 TB/mo** | Read latency | Notes |
|---|---|---|---|---|
| S3 Standard | $0.023 | **~$29** | instant | overkill for archive |
| S3 Standard-IA | $0.0125 | **~$16** | instant | + $0.01/GB retrieval fee |
| **Glacier Instant Retrieval** ⭐ | $0.004 | **~$5** | **milliseconds** | best fit for "occasional access" |
| Glacier Flexible | $0.0036 | **~$4.5** | minutes–hours | must "restore" before read |
| Glacier Deep Archive | $0.00099 | **~$1.25** | up to 12 h | cheapest; for true cold backup |

⭐ The script defaults to **Glacier Instant Retrieval** for video — you get millisecond reads but pay ~6× less than Standard.

### What it costs to *read it back* later (Glacier IR)

- Retrieval: **$0.03 / GB** → reading all 1.25 TB once ≈ **$38**.
- Egress to the internet (if you download out of AWS): **$0.09 / GB** → all 1.25 TB ≈ **$115**.
- Reading within AWS (e.g., an EC2/Lambda in the same region) avoids the egress charge.

So storing is nearly free; the only real money shows up if you bulk-download everything *out* of AWS.

### Scaling cheat-sheet (video, Glacier Instant Retrieval @ $0.004/GB/mo)

| Meetings (~250 MB each) | Total | Storage / month |
|---|---|---|
| 100 | 25 GB | ~$0.10 |
| 1,000 | 250 GB | ~$1.00 |
| 5,000 | 1.25 TB | ~$5.00 |
| 20,000 | 5 TB | ~$20.00 |

The script prints your **actual** measured GB and a cost estimate at the end of every run, so you'll get a precise number for your data rather than this assumption.

### Want it even cheaper?

If most of this is "store and forget," set `VIDEO_STORAGE_CLASS=DEEP_ARCHIVE` in `.env` → **~$1.25/mo** for the same 1.25 TB (trade-off: reads take hours and need a restore step). Or add an S3 **Lifecycle rule** to auto-move objects from Glacier IR → Deep Archive after, say, 90 days.

---

### Cost assumptions

Numbers assume **~250 MB per hour-long meeting** and **us-east-1** list pricing (other regions are within ~10–20%). Video size varies with meeting length and quality — short calls are far smaller. The `--dry-run` and end-of-run summary give you the real figures for your account.
