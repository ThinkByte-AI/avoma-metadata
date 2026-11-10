# Avoma Metadata

Tools and data for GrowthByte's Avoma meeting archive: copying recordings, transcripts and AI notes from Avoma
into S3 (`s3://avoma-archive-growthbyte`, `ap-south-1`), and the **Meeting Intelligence** app for searching
and asking questions about them.

## What's in this repo

| Folder | What it is |
| --- | --- |
| [`meeting-intel/`](meeting-intel/) | **Meeting Intelligence app**: search, read, listen to and ask an AI about every meeting (FastAPI + Next.js + Postgres) |
| [`archiver/`](archiver/) | Scripts that copy Avoma **recordings and transcripts** to S3, plus storage and cost estimates |
| [`notes-puller/`](notes-puller/) | Scripts that pull Avoma **AI notes**, locally or from a temporary EC2 server |
| [`clients/sigma/`](clients/sigma/) | All Sigma (SigmaInfo) client meetings in one place: per-meeting notes and a combined summary |
| [`data/`](data/) | Meeting lists (`metadata/`) and the pulled AI notes (`notes/`) |
| [`docs/`](docs/) | AWS account and access details, and the app's design and build plan |

## Quick start

All scripts run **from the repo root**, where your `.env` and API key files live.

```powershell
pip install -r requirements.txt
copy .env.example .env        # then fill in the values

python archiver/avoma_to_s3.py --from 2024-01-01 --to 2024-12-31 --dry-run
python notes-puller/pull_notes.py --dry-run
python clients/sigma/extract_sigma.py
```

For the app, see [`meeting-intel/README.md`](meeting-intel/README.md): `docker compose up -d` inside `meeting-intel/`,
then open http://localhost:3100.

## Secrets

`.env`, `keys*.txt` and `*api key*.txt` stay on your machine and are never committed (see [`.gitignore`](.gitignore)).
Copy [`.env.example`](.env.example) to get started.
