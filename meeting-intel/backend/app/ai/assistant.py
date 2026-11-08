"""AI meeting assistant: the model searches the archive through a tool, then answers only from numbered sources."""
import logging
import re
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import exists, func, or_, select, tuple_
from sqlalchemy.orm import Session

from app.api.schemas import UtcDT
from app.auth.access import accessible_meeting_ids
from app.errors import ApiError
from app.models import MeetingParticipant, Participant, TranscriptSegment, User
from app.search.schemas import SearchFilters, SearchRequest
from app.search.service import _like, search

log = logging.getLogger("app.ai.assistant")

MAX_TOOL_ROUNDS = 4
MAX_SOURCES_PER_CALL = 15
DEFAULT_SOURCES_PER_CALL = 8
MAX_TOKENS = 2000
NO_EVIDENCE_ANSWER = "I couldn't find anything in the meeting archive about that."
FALLBACK_ANSWER = "I couldn't complete the search for that question. Please rephrase it or narrow it down."
FORCE_ANSWER = "Stop searching now. Answer the question using only the numbered sources you already have."

SYSTEM_PROMPT = """You are the meeting archive assistant. Today's date is {today}.
You answer questions about past meetings using ONLY passages returned by the search_meetings tool.

Rules:
- Always call search_meetings before answering. Search again with different words if the first results are weak.
- Use the speaker / participant / date filters when the question names a person or a time period.
- Every factual statement must cite its source number in square brackets, e.g. "Revenue grew 5% [3]".
- Use only the numbered sources. Never invent names, dates, numbers, quotes, decisions or meetings.
- If the sources do not answer the question, say so plainly.
- When comparing across meetings or months, group the answer by meeting or month and keep their dates.
- Be concise. Use short paragraphs or bullet points in Markdown."""

TOOL_SPEC = {
    "toolSpec": {
        "name": "search_meetings",
        "description": (
            "Search the meeting archive (transcripts and meeting notes). Returns numbered passages with the meeting "
            "title, date, speaker and timestamp. Use plain keywords or a short phrase as the query."
        ),
        "inputSchema": {"json": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to look for, e.g. 'pricing decision'"},
                "speaker": {"type": "string", "description": "Only passages spoken by this person (name)"},
                "participant": {"type": "string", "description": "Only meetings this person attended (name)"},
                "date_from": {"type": "string", "description": "YYYY-MM-DD, inclusive"},
                "date_to": {"type": "string", "description": "YYYY-MM-DD, inclusive"},
                "limit": {"type": "integer", "description": f"Passages to return (1-{MAX_SOURCES_PER_CALL})"},
            },
            "required": ["query"],
        }},
    }
}


class HistoryTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    filters: SearchFilters | None = None
    history: list[HistoryTurn] = Field(default_factory=list, max_length=6)


class Citation(BaseModel):
    n: int
    meeting_id: uuid.UUID
    subject: str
    start_at: UtcDT | None
    speaker_name: str | None
    start_sec: float | None
    segment_id: int
    excerpt: str


class AskResponse(BaseModel):
    answer_markdown: str
    citations: list[Citation]
    evidence_found: bool
    model: str
    took_ms: int


@dataclass
class Source:
    n: int
    segment_id: int
    meeting_id: uuid.UUID
    subject: str
    start_at: datetime | None
    speaker_name: str | None
    section: str | None
    start_sec: float | None
    text: str
    before: str | None = None
    after: str | None = None


def _fmt_time(sec: float | None) -> str:
    if sec is None:
        return "—"
    s = int(sec)
    h, m, s = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _parse_date(v) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def _resolve_people(db: Session, user: User, name: str) -> list[int]:
    like = _like(name.strip())
    visible = accessible_meeting_ids(user)
    return list(db.scalars(
        select(Participant.id)
        .where(or_(Participant.name.ilike(like, escape="\\"), Participant.email.ilike(like, escape="\\"),
                   func.similarity(Participant.name, name) > 0.4),
               exists().where(MeetingParticipant.participant_id == Participant.id,
                              MeetingParticipant.meeting_id.in_(visible)))
        .order_by(func.similarity(Participant.name, name).desc())
        .limit(5)
    ))


class _Session:
    """One ask: holds the numbered sources across tool calls."""

    def __init__(self, db: Session, user: User, base_filters: SearchFilters | None, embedder):
        self.db, self.user, self.embedder = db, user, embedder
        self.base = base_filters or SearchFilters()
        self.sources: dict[int, Source] = {}
        self.by_segment: dict[int, int] = {}
        self._ctx: dict[int, tuple[str | None, str | None]] = {}

    def run_tool(self, inp: dict) -> str:
        query = str(inp.get("query") or "").strip()[:500]
        if not query:
            return "The query was empty. Provide keywords to search for."
        f = self.base.model_copy(deep=True)
        speaker = str(inp.get("speaker") or "").strip()
        if speaker:
            ids = _resolve_people(self.db, self.user, speaker)
            if not ids:
                return f"No participant matching '{speaker}' was found in the archive."
            f.speaker_ids = sorted(set(f.speaker_ids) | set(ids))  # spoken by any matching person
        participant = str(inp.get("participant") or "").strip()
        if participant:
            ids = _resolve_people(self.db, self.user, participant)
            if not ids:
                return f"No participant matching '{participant}' was found in the archive."
            f.participant_ids = sorted(set(f.participant_ids) | {ids[0]})  # best match attended
        if (d := _parse_date(inp.get("date_from"))) is not None:
            f.date_from = d
        if (d := _parse_date(inp.get("date_to"))) is not None:
            f.date_to = d
        try:
            limit = max(1, min(MAX_SOURCES_PER_CALL, int(inp.get("limit") or DEFAULT_SOURCES_PER_CALL)))
        except (TypeError, ValueError):
            limit = DEFAULT_SOURCES_PER_CALL

        resp = search(self.db, self.user, SearchRequest(q=query, filters=f, mode="auto", page_size=20),
                      self.embedder, record_history=False)
        picked: list[tuple] = []
        for hit in resp.results:
            for m in hit.matches:
                picked.append((hit.meeting, m))
                if len(picked) >= limit:
                    break
            if len(picked) >= limit:
                break
        if not picked:
            return "No matching passages found."
        self._add_context([m.segment_id for _, m in picked])
        lines = []
        for meeting, m in picked:
            src = self._source_for(meeting, m)
            day = src.start_at.date().isoformat() if src.start_at else "unknown date"
            who = f"Speaker: {src.speaker_name}" if src.speaker_name else f"Meeting notes: {src.section or 'Notes'}"
            block = [f"[{src.n}] Meeting: {src.subject} | Date: {day} | {who} | Time: {_fmt_time(src.start_sec)}"]
            if src.before:
                block.append(f"  (before) {src.before}")
            block.append(f"  {src.text}")
            if src.after:
                block.append(f"  (after) {src.after}")
            lines.append("\n".join(block))
        return "\n\n".join(lines)

    def _add_context(self, seg_ids: list[int]) -> None:
        rows = self.db.execute(select(TranscriptSegment.id, TranscriptSegment.meeting_id, TranscriptSegment.kind,
                                      TranscriptSegment.seq).where(TranscriptSegment.id.in_(seg_ids))).all()
        keys = [(r.meeting_id, r.seq - 1) for r in rows if r.kind == "utterance"] + \
               [(r.meeting_id, r.seq + 1) for r in rows if r.kind == "utterance"]
        neighbours = {}
        if keys:
            for mid, seq, spk, txt in self.db.execute(
                select(TranscriptSegment.meeting_id, TranscriptSegment.seq, TranscriptSegment.speaker_name,
                       TranscriptSegment.text)
                .where(TranscriptSegment.kind == "utterance",
                       tuple_(TranscriptSegment.meeting_id, TranscriptSegment.seq).in_(keys))
            ):
                neighbours[(mid, seq)] = f"{spk or 'Unknown'}: {txt[:400]}"
        for r in rows:
            if r.kind == "utterance":
                self._ctx[r.id] = (neighbours.get((r.meeting_id, r.seq - 1)), neighbours.get((r.meeting_id, r.seq + 1)))

    def _source_for(self, meeting, m) -> Source:
        if m.segment_id in self.by_segment:
            return self.sources[self.by_segment[m.segment_id]]
        n = len(self.sources) + 1
        before, after = self._ctx.get(m.segment_id, (None, None))
        src = Source(n=n, segment_id=m.segment_id, meeting_id=meeting.id, subject=meeting.subject,
                     start_at=meeting.start_at, speaker_name=m.speaker_name, section=m.section,
                     start_sec=m.start_sec, text=m.text, before=before, after=after)
        self.sources[n] = src
        self.by_segment[m.segment_id] = n
        return src


_CITE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def clean_citations(answer: str, known: set[int]) -> tuple[str, list[int]]:
    """Drop citation numbers that point at no source; return the cleaned text and cited numbers in order."""
    order: list[int] = []

    def repl(m: re.Match) -> str:
        nums = [int(x) for x in re.split(r"\s*,\s*", m.group(1))]
        keep = [n for n in nums if n in known]
        for n in keep:
            if n not in order:
                order.append(n)
        return "".join(f"[{n}]" for n in keep)

    text = _CITE.sub(repl, answer)
    text = re.sub(r"[ \t]+([.,;:!?])", r"\1", text)
    return text.strip(), order


def _messages(req: AskRequest) -> list[dict]:
    turns = [(t.role, t.content) for t in req.history if t.content.strip()] + [("user", req.question)]
    out: list[dict] = []
    for role, content in turns:
        if not out and role != "user":
            continue  # a conversation must start with the user
        if out and out[-1]["role"] == role:
            out[-1]["content"][0]["text"] += "\n\n" + content
        else:
            out.append({"role": role, "content": [{"text": content}]})
    return out


def _text_of(message: dict) -> str:
    return "".join(b["text"] for b in message.get("content", []) if "text" in b)


def ask(db: Session, user: User, req: AskRequest, embedder, chat) -> AskResponse:
    t0 = time.perf_counter()
    session = _Session(db, user, req.filters, embedder)
    messages = _messages(req)
    system = SYSTEM_PROMPT.format(today=datetime.now(UTC).date().isoformat())
    answer: str | None = None
    try:
        for rnd in range(MAX_TOOL_ROUNDS + 1):
            out = chat.converse(system, messages, [TOOL_SPEC], MAX_TOKENS)
            msg = out["message"]
            messages.append(msg)
            uses = [b["toolUse"] for b in msg.get("content", []) if "toolUse" in b]
            if uses and rnd < MAX_TOOL_ROUNDS:
                results = [{"toolResult": {"toolUseId": u["toolUseId"],
                                           "content": [{"text": session.run_tool(u.get("input") or {})}]}}
                           for u in uses]
                if rnd + 1 == MAX_TOOL_ROUNDS:
                    results.append({"text": FORCE_ANSWER})
                messages.append({"role": "user", "content": results})
                continue
            answer = None if uses else _text_of(msg)
            break
    except ApiError:
        raise
    except Exception as e:
        log.warning("assistant model call failed", extra={"error": f"{type(e).__name__}: {e}"})
        raise ApiError(502, "ai_unavailable", "The AI assistant is unavailable right now. Please try again.") from None

    took = int((time.perf_counter() - t0) * 1000)
    model_id = getattr(chat, "model_id", "unknown")
    if answer is None:
        return AskResponse(answer_markdown=FALLBACK_ANSWER, citations=[], evidence_found=False, model=model_id,
                           took_ms=took)
    if not session.sources:
        return AskResponse(answer_markdown=NO_EVIDENCE_ANSWER, citations=[], evidence_found=False, model=model_id,
                           took_ms=took)
    text, cited = clean_citations(answer, set(session.sources))
    citations = [
        Citation(n=n, meeting_id=s.meeting_id, subject=s.subject, start_at=s.start_at, speaker_name=s.speaker_name,
                 start_sec=s.start_sec, segment_id=s.segment_id, excerpt=s.text[:600])
        for n in cited if (s := session.sources[n])
    ]
    log.info("assistant answered", extra={"sources": len(session.sources), "cited": len(citations), "took_ms": took})
    return AskResponse(answer_markdown=text, citations=citations, evidence_found=bool(citations), model=model_id,
                       took_ms=took)
