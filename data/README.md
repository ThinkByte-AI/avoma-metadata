# Data

Private business data: meeting lists and AI notes from GrowthByte's Avoma accounts.

| Folder | What it is | Used by |
| --- | --- | --- |
| `metadata/` | One CSV of meetings per Avoma account (title, date, duration, owner, attendees) | `notes-puller/`, the Meeting Intelligence app (mounted read-only) |
| `notes/` | AI notes per meeting (`<uuid>.json` raw, `<uuid>.md` readable), `notes_index.csv`, and `worklist.csv` (the meetings to pull) | `notes-puller/`, `clients/sigma/` |

The full archive (recordings, transcripts, all notes) lives in S3: `s3://avoma-archive-growthbyte/avoma/<YYYY>/<MM>/<uuid>/`.
