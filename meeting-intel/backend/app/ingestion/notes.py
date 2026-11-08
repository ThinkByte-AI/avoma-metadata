"""Parse Avoma notes.md: title, date, sections and topic headings."""
import re
from dataclasses import dataclass
from datetime import datetime

from app.ingestion.metadata import parse_dt

NON_TOPIC_HEADINGS = {"participants", "key takeaways", "action items", "next steps", "summary"}
_DATE_LINE = re.compile(r"^_(?P<dt>[^_]+)_$")


@dataclass
class NoteSection:
    heading: str
    text: str


@dataclass
class ParsedNotes:
    title: str | None
    start_at: datetime | None
    sections: list[NoteSection]
    topics: list[str]
    markdown: str


def parse_notes(md: str) -> ParsedNotes:
    title: str | None = None
    start_at: datetime | None = None
    sections: list[NoteSection] = []
    heading: str | None = None
    body: list[str] = []

    def flush() -> None:
        if heading is not None:
            sections.append(NoteSection(heading, "\n".join(body).strip("\n").rstrip()))

    for line in (md or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            flush()
            heading, body = stripped[3:].strip(), []
        elif stripped.startswith("# ") and title is None and heading is None:
            title = stripped[2:].strip() or None
        elif heading is None and start_at is None and (m := _DATE_LINE.match(stripped)):
            start_at = parse_dt(m["dt"])
        elif heading is not None:
            body.append(line.rstrip())
    flush()

    topics: list[str] = []
    for s in sections:
        if s.heading.strip().lower() in NON_TOPIC_HEADINGS:
            continue
        t = s.heading.strip().title()[:80]
        if t and t not in topics:
            topics.append(t)

    return ParsedNotes(title=title, start_at=start_at, sections=sections, topics=topics, markdown=md or "")
