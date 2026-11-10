# Sigma (SigmaInfo)

Every Avoma meeting with Sigma, pulled from the archive.

| File | What it is |
| --- | --- |
| `sigma_notes.md` | All meeting summaries in one document, oldest first |
| `sigma_meetings.csv` | Index: date, subject, meeting id, attendees, whether notes exist, S3 path |
| `meetings/` | Each meeting's raw notes (`.json`) and readable summary (`.md`) |
| `extract_sigma.py` | Rebuilds everything above from S3 |

To refresh, run from the repo root:

```powershell
python clients/sigma/extract_sigma.py
```

It selects meetings whose subject mentions "sigma" from `data/notes/worklist.csv`.
