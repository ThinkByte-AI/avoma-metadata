# Meeting Intelligence Dashboard — Design

Status: approved by the user on 2026-11-08 ("i want that build that"). Part A records how the spec maps onto the real archive and the build choices made. Part B is the user's spec, verbatim. Where A and B differ, A wins.

---

## Part A — Real data and build decisions

### A1. What the archive actually contains (checked 2026-11-08, read-only)

- Bucket `avoma-archive-growthbyte`, region `ap-south-1`, account 381491857586.
- Layout: `avoma/<YYYY>/<MM>/<meeting-uuid>/<file>`. 3,152 meeting folders, Feb 2024 – Feb 2026.
- Other prefix: `_bootstrap/` (EC2 run logs). Not meetings; must be classified as `unknown` and ignored.
- Files per folder (counts across the bucket):

| File | Count | Total size | Storage class | Notes |
| --- | --- | --- | --- | --- |
| `transcript.json` | 3,152 | 0.34 GB | STANDARD | see A2 |
| `notes.md` | 3,109 | 0.01 GB | STANDARD | Avoma AI notes as markdown |
| `notes.json` | 3,109 | 0.12 GB | STANDARD | same notes as Avoma block JSON; not needed |
| `recording.mp3` | 3,084 | 53 GB | GLACIER_IR | audio; ContentType stored as `binary/octet-stream` |
| `recording.mp4` | 3,084 | 162 GB | GLACIER_IR | video |

- 68 meetings have a transcript but no recording. No meeting lacks a transcript, so no speech-to-text workflow is built (the "missing transcript" state is still tracked and shown).

### A2. `transcript.json` shape

A JSON list with one object:

```json
[{
  "uuid": "<transcription uuid>",
  "meeting_uuid": "<meeting uuid>",
  "modified": "2025-02-11T14:48:17.051057Z",
  "transcription_vtt_url": "<expired Avoma URL — ignore>",
  "speakers": [{"id": 0, "name": "Charan Kumar", "email": "x@y.com", "is_rep": true}],
  "transcript": [
    {"speaker_id": 0, "transcript": "Hi, Suresh. Good evening.", "timestamps": [20.635, 20.9, ...], "speaker_distance": 1.0}
  ]
}]
```

- `timestamps` = start time in seconds of each word of that utterance (one per word).
- `is_rep: true` = internal team member; `false` = external (client).
- `email` may be empty or missing; `speaker_id` may reference no listed speaker.

### A3. `notes.md` shape

```
# <meeting title>
_<ISO start time>_

## Participants
- ThinkByte: Name, Name
- External Name

## Key Takeaways
- ...

## Action Items
- Person
    - task

## <Topic heading, e.g. "Spending and Revenue">
- ...
```

Headings other than Participants / Key Takeaways / Action Items are the meeting's topics.

### A4. Meeting metadata lives outside S3

Titles, start times, durations and owners are not in S3. They are in the repo's CSV files (all 3,152 S3 meetings are covered):

- `csv_files/meetings_deduped.csv`, `meetings_deduped2.csv`, `meetings_deduped3.csv`, `meetings_deduped4.csv` — columns `uuid,subject,start,duration_min,video_ready,transcript_ready,recording_uuid,transcription_uuid,owner_key,n_accounts`. First file wins on repeats.
- Every other `csv_files/meetings_*.csv` that has an `owner` column — one row per meeting visible in that team member's Avoma account. The set of `owner` values per uuid = the meeting's **accounts** (who could see it in Avoma).

Ingestion reads these from a configured local directory (`METADATA_DIR`). If a meeting has no CSV row, fall back to the `notes.md` title/date, and duration = last word timestamp.

### A5. Build decisions (Claude's calls; user may override)

| Area | Decision | Why |
| --- | --- | --- |
| Location | New folder `meeting-intel/` (`backend/`, `frontend/`, `docker-compose.yml`) | Existing archival scripts and root `.env` stay untouched |
| Frontend | Next.js (App Router) + TypeScript + Tailwind + shadcn/ui + lucide + Recharts + TanStack Query | As spec |
| Backend | Python FastAPI, SQLAlchemy 2, Alembic, boto3 | As spec |
| Search | PostgreSQL only: `tsvector` full text + `pg_trgm` fuzzy names + `pgvector` semantic, fused with Reciprocal Rank Fusion. Behind a `SearchService` interface | ~3k meetings / ~300k segments; OpenSearch would add $100+/month for no gain at this size |
| Background work | Postgres-backed job table + a worker process (no SQS) | One fewer AWS service; pause/resume/retry are simple status flips |
| Embeddings | Bedrock `amazon.titan-embed-text-v2:0`, 1024 dims, normalized, `ap-south-1` | Verified working 2026-11-08 |
| AI model | Bedrock `zai.glm-5` (GLM 5, on-demand in `ap-south-1`, processing stays in India), called through the model-agnostic Converse API so it is swappable by config | User asked for GLM (2026-11-08). Verified 2026-11-08: plain replies and tool calls work (~2 s). `zai.glm-4.7` also works; `zai.glm-4.7-flash` produced poor tool arguments; `global.zai.glm-5.3` is not enabled for this account |
| Audio | Play `recording.mp3` via 15-minute presigned URL with `ResponseContentType=audio/mpeg`; mp4 offered as download only | mp3 is ~1/3 the size; stored content type would not play |
| Auth | Email + password (argon2), JWT in an httpOnly cookie; Next.js proxies `/api/*` to the backend so it is same-origin | No CORS, no token in JS |
| Access rule | Admin: everything. Standard user: meetings whose accounts include the user's `account_label`, or where the user's email is a participant. Admin can set a user's scope to `all` | Mirrors who could see the meeting in Avoma |
| Summaries / decisions / action items | Taken from Avoma's `notes.md` (already generated), indexed as `note` segments and shown on the meeting page | Real data, no extra LLM cost |
| Topics | `notes.md` topic headings, normalised, stored per meeting | Real "most discussed topics" without a model |
| Dev mock mode | `APP_MODE=dev-mock` seeds 5 synthetic meetings titled `[SAMPLE] …` and shows a "Development mode — sample data" banner. Never on by default | Spec section 9 |
| AWS credentials | Standard boto3 chain (env vars, profile, IAM role). Local dev reuses the existing key via env; a least-privilege IAM policy is provided for a dedicated role | The current key is Kaushik's admin key |
| Writes to S3 | None. The app only lists, reads and presigns | Spec: preserve originals |

### A6. Non-goals for this build

- Deploying to AWS (needs the user's go-ahead on hosting and cost). The build ships production Dockerfiles, a prod compose profile and a deployment guide.
- Creating IAM users/roles in the account. A policy JSON is provided.
- Speech-to-text (no meeting lacks a transcript).
- OpenSearch and SQS (see A5).

---

## Part B — The user's spec (verbatim)

# Project: AI-Powered Meeting Intelligence Dashboard

## 1. Project Overview

Build a production-ready AI-powered Meeting Intelligence Dashboard that connects to my existing AWS account and retrieves approximately 2–2.5 years of historical meeting data.

The AWS account contains:
- Meeting audio recordings
- Call recordings
- Meeting transcripts
- Meeting metadata
- Participant information
- Meeting-related JSON and other files

The main objective is to create a centralized platform where users can search, discover, retrieve, listen to, and analyse historical meetings using names, email addresses, keywords, topics, dates, and natural-language questions.

This must be a fully functional application, not just a UI prototype.

## 2. Recommended Technology Stack

### Frontend
- Next.js
- React
- TypeScript
- Tailwind CSS
- Shadcn UI
- Lucide icons
- Recharts for analytics

### Backend
- Python FastAPI
- REST APIs
- Background workers
- AWS SDK (Boto3)

### Database
- PostgreSQL / AWS RDS
- Amazon OpenSearch for full-text and semantic search

### AWS Services
- Amazon S3 for audio and transcript storage
- IAM roles for secure AWS access
- Amazon SQS for background processing
- Amazon Bedrock for embeddings and AI-powered retrieval, if configured
- CloudWatch for monitoring

## 3. Main Application Modules

### Module 1: Dashboard Overview

Create an analytics dashboard displaying:

- Total meetings
- Total recordings
- Total participants
- Total transcript records
- Total audio storage
- Total meeting duration
- Meetings by month
- Meetings by participant
- Most frequently discussed topics
- Recent meetings
- Search activity

All statistics must come from actual indexed data.

### Module 2: Universal Meeting Search

This is the most important module.

Create a prominent global search bar that supports the following search methods:

**A. Search by person**
- Participant name
- Email address
- Speaker name
- Partial name matching

Example: John Wilson

**B. Search by meeting**
- Meeting title
- Meeting ID
- Meeting subject
- Meeting description

Example: Client Onboarding Discussion

**C. Search by keywords**
- Revenue
- Marketing
- AWS
- Project deadlines
- Pricing

Search across the complete transcript content.

**D. Semantic search**

Allow users to search using natural-language questions.

Examples:
- What did John say about project deadlines?
- Which meetings discussed revenue growth?
- What was decided about the marketing strategy?
- What did we discuss about AWS infrastructure?
- Find conversations where someone mentioned increasing the budget.

The search engine should understand meaning, not just exact words.

**E. Search by date**

Support:
- Today
- Last 7 days
- Last 30 days
- Last 6 months
- Last year
- Custom date range
- Entire historical archive

**F. Combined search**

Allow multiple filters simultaneously.

Example:
Find all meetings where John Wilson discussed revenue between January and December 2025.

### Module 3: Advanced Search Filters

Provide filters for:

- Participant
- Meeting date
- Meeting title
- Speaker
- Meeting duration
- Recording availability
- Transcript availability
- Keywords
- Meeting owner

Allow users to combine filters and clear them easily.

### Module 4: Search Results

Each result should display:

- Meeting title
- Meeting ID
- Meeting date
- Meeting duration
- Participants
- Matching transcript excerpt
- Speaker name
- Match timestamp
- Recording availability
- Transcript availability

Highlight the matching keyword or relevant sentence.

Support pagination, sorting, and relevance ranking.

### Module 5: Meeting Details Page

When a user opens a meeting, display:

**Meeting Information**
- Meeting title
- Meeting ID
- Date and time
- Duration
- Participants
- Owner

**Audio Player**
- Play and pause
- Volume control
- Playback speed
- Seek bar
- Current timestamp
- Download option, subject to permissions

**Transcript Viewer**
- Complete transcript
- Speaker identification
- Timestamp for every segment
- Search within transcript
- Highlight matching text
- Click a transcript segment to jump to the corresponding audio timestamp

Audio and transcript playback must remain synchronized.

### Module 6: AI Meeting Assistant

Create an AI assistant that can answer questions using the indexed meeting archive.

Example questions:

- What did John promise in his previous meetings?
- Summarize all discussions about the product launch.
- What decisions were made about pricing?
- Which meetings discussed pending tasks?
- What commitments were made by each participant?
- Compare discussions about revenue across different months.

Important requirements:
- Retrieve relevant transcript segments before generating answers.
- Provide meeting title, date, speaker, and timestamp as citations.
- Allow users to open the original recording from an AI-generated answer.
- Never fabricate meeting information.
- Clearly indicate when no relevant evidence is found.

### Module 7: Participant Directory

Create a participant management page.

Display:
- Participant name
- Email
- Total meetings attended
- Total speaking duration, where available
- First meeting date
- Last meeting date
- Recent meetings

Clicking a participant should show all associated meetings and transcript mentions.

### Module 8: Historical Data Ingestion

Build an ingestion pipeline that connects to my existing AWS S3 bucket.

Requirements:

1. Connect to AWS using IAM roles or securely configured credentials.
2. Scan all objects in the specified bucket and prefixes.
3. Identify audio recordings, transcripts, JSON files, and metadata.
4. Extract meeting IDs and participant details.
5. Associate audio recordings with their respective transcripts.
6. Identify duplicate meetings using meeting IDs and other reliable identifiers.
7. Store meeting metadata in PostgreSQL.
8. Split transcripts into searchable segments while preserving timestamps and speakers.
9. Generate embeddings for semantic search.
10. Index metadata and transcript segments in OpenSearch.
11. Track processing status for every meeting.
12. Support retrying failed records.
13. Support incremental synchronization for newly added files.
14. Avoid downloading entire recordings unnecessarily.
15. Preserve original files in S3.

Do not assume that every S3 object is a meeting. Build file classification and validation.

If transcripts are missing, identify those records and optionally provide a speech-to-text processing workflow.

Do not reprocess already indexed recordings unless required.

### Module 9: Database Design

Create the following PostgreSQL tables:

- meetings
- participants
- meeting_participants
- recordings
- transcripts
- transcript_segments
- ingestion_jobs
- search_history
- users
- audit_logs

Use appropriate foreign keys, indexes, constraints, and timestamps.

Use meeting IDs as deduplication keys wherever reliable.

### Module 10: User Authentication and Permissions

Implement secure authentication.

Support:
- Administrator
- Standard user

Administrators can:
- View archive analytics
- Manage ingestion
- Access permitted meetings
- Monitor indexing
- View system status

Standard users can:
- Search accessible meetings
- View transcripts
- Play recordings
- Use the AI meeting assistant

Enforce authorization on backend APIs and audio retrieval, not just the frontend.

### Module 11: Admin Ingestion Panel

Create an administration page showing:

- AWS connection status
- S3 bucket and configured prefixes
- Total objects scanned
- Audio files discovered
- Transcript files discovered
- Meetings identified
- Meetings indexed
- Failed records
- Duplicate records
- Processing progress
- Last synchronization time

Provide buttons to:
- Start initial ingestion
- Pause processing
- Resume processing
- Retry failed records
- Start incremental synchronization

Do not allow destructive operations on original S3 files.

## 4. UI/UX Requirements

Build a modern, professional SaaS dashboard.

Design inspiration:
- Linear
- Notion
- Stripe Dashboard
- Modern analytics platforms

Design requirements:
- Clean and minimal interface
- Professional typography
- Consistent spacing
- Responsive layout
- Sidebar navigation
- Light and dark themes
- Global search accessible from every page
- Loading skeletons
- Empty states
- Error states
- Search suggestions
- Search history
- Clear filter controls

Sidebar navigation:

1. Overview
2. Search Meetings
3. All Meetings
4. Participants
5. AI Assistant
6. Analytics
7. Data Ingestion
8. Settings

Make the search experience the central focus of the application.

## 5. Search Engine Requirements

Implement hybrid search combining:

1. Exact metadata matching
2. Full-text keyword search
3. Semantic vector search
4. Participant filtering
5. Date filtering

Use relevance ranking to prioritize the most useful results.

For natural-language questions, retrieve multiple relevant transcript segments and group them by meeting.

Always return source references and timestamps.

## 6. API Endpoints

Create well-structured REST APIs.

Suggested endpoints:

- GET /api/dashboard/stats
- GET /api/meetings
- GET /api/meetings/{meeting_id}
- GET /api/meetings/{meeting_id}/transcript
- GET /api/meetings/{meeting_id}/recording
- GET /api/participants
- GET /api/participants/{participant_id}
- POST /api/search
- POST /api/ai/ask
- GET /api/search/history
- POST /api/ingestion/start
- GET /api/ingestion/status
- POST /api/ingestion/retry
- POST /api/ingestion/sync

Use pagination, validation, authentication, and consistent error responses.

## 7. Security and Performance

- Use IAM roles wherever possible.
- Never expose AWS access keys in frontend code.
- Use short-lived presigned S3 URLs for authorized audio playback.
- Enforce user-level access control.
- Encrypt sensitive data in transit and at rest.
- Avoid loading full recordings into application memory.
- Use pagination for large search results.
- Cache frequently accessed metadata.
- Add database and OpenSearch indexes.
- Implement retries and structured logging.
- Handle thousands of meetings and potentially millions of transcript segments efficiently.

## 8. Development Strategy

Build this application in the following order:

**Phase 1: Foundation**
- Project structure
- Authentication
- Database schema
- AWS connection
- S3 scanning

**Phase 2: Data Processing**
- File classification
- Meeting identification
- Deduplication
- Transcript processing
- Database ingestion

**Phase 3: Search**
- OpenSearch setup
- Full-text search
- Semantic embeddings
- Hybrid search
- Search filters

**Phase 4: Dashboard**
- Overview
- Search interface
- Results page
- Meeting details
- Audio player
- Transcript viewer

**Phase 5: AI Features**
- AI meeting assistant
- Cross-meeting questions
- Summaries
- Decisions and action items
- Source citations

**Phase 6: Production**
- Permissions
- Performance optimization
- Error handling
- Testing
- Deployment
- Monitoring

## 9. Important Development Instructions

- First inspect the existing repository and understand its architecture.
- Do not overwrite or unnecessarily replace existing code.
- Create a clear frontend/backend project structure.
- Use environment variables for all credentials and configurations.
- Create `.env.example`.
- Provide database migrations.
- Provide Docker configuration for local development.
- Write reusable components and modular services.
- Add unit and integration tests.
- Never use dummy data as actual AWS records.
- If AWS credentials are unavailable, implement a clear connection configuration screen and use mock data only in an explicitly labelled development mode.
- Do not hardcode bucket names, meeting IDs, participants, or AWS credentials.
- Do not claim ingestion or indexing is complete until verified.

## 10. Expected Final Deliverable

A fully functional Meeting Intelligence platform where I can:

1. Connect my existing AWS account.
2. Ingest approximately two years of historical meeting data.
3. Search using participant names and email addresses.
4. Search meeting titles and keywords.
5. Ask natural-language questions across all historical transcripts.
6. Filter meetings by date and participant.
7. Retrieve the exact matching transcript sections.
8. Play the original recording from the matching timestamp.
9. View complete meeting transcripts.
10. Analyse historical conversations using AI.

**Final objective:** Create one centralized search platform for all historical meeting recordings, calls, transcripts, and participant conversations, with fast, accurate, secure retrieval.

Start by inspecting the repository and AWS data structure. Then implement the application incrementally, validating each phase before proceeding to the next.
