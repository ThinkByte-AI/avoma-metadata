# Notes puller

Pulls Avoma **AI notes / summaries** for the team's meetings and stores them next to the transcripts in S3
(`avoma/<YYYY>/<MM>/<uuid>/notes.json` and `notes.md`), or locally in [`../data/notes/`](../data/notes/).

Run everything **from the repo root**.

| Script | What it does |
| --- | --- |
| `pull_notes.py` | The puller: resumable and rate-limited, local or straight to S3 (`--s3`) |
| `probe_notes.py` | A few read-only calls to check the notes endpoint and API key format |
| `launch_ec2.py` | Starts a temporary EC2 server that runs `pull_notes.py --s3` inside AWS, then terminates itself |
| `cleanup_ec2.py` | Afterwards: shows the run log, terminates any leftover server, deletes the uploaded key files from S3 |

```powershell
python notes-puller/pull_notes.py --dry-run      # show the plan, no API calls
python notes-puller/pull_notes.py --limit 3      # smoke test
python notes-puller/pull_notes.py --s3 --worklist data/notes/worklist.csv
```

Inputs: `avoma api key.txt` (repo root, never committed), meeting lists in `data/metadata/`,
and the work-list `data/notes/worklist.csv`.
