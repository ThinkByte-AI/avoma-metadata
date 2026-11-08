"""Hybrid meeting search: full text + vector + metadata, fused with Reciprocal Rank Fusion, grouped by meeting."""
import logging
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime, time as dtime, timedelta

from sqlalchemy import Text, case, exists, func, literal, or_, select, text
from sqlalchemy.orm import Session

from app.api.schemas import _iso_z
from app.api.summaries import build_summaries
from app.auth.access import accessible_meeting_clause
from app.config import get_settings
from app.models import Meeting, MeetingParticipant, Participant, SearchHistory, TranscriptSegment, User
from app.search.schemas import MeetingHit, SearchFilters, SearchRequest, SearchResponse, SegmentMatch

log = logging.getLogger("app.search")

RRF_K = 60
CANDIDATES = 200
METADATA_CANDIDATES = 100
MATCHES_PER_MEETING = 3
METADATA_WEIGHT = 2.0
HL_START, HL_STOP = "«HL«", "»HL»"
_PRESET_DAYS = {"7d": 7, "30d": 30, "6m": 182, "1y": 365}

TS, MP, P = TranscriptSegment, MeetingParticipant, Participant


def _like(q: str) -> str:
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def date_range(f: SearchFilters, now: datetime) -> tuple[datetime | None, datetime | None]:
    if f.date_from or f.date_to:
        start = datetime.combine(f.date_from, dtime.min, UTC) if f.date_from else None
        end = datetime.combine(f.date_to + timedelta(days=1), dtime.min, UTC) if f.date_to else None
        return start, end
    if f.date_preset == "today":
        return datetime.combine(now.date(), dtime.min, UTC), None
    if f.date_preset in _PRESET_DAYS:
        return now - timedelta(days=_PRESET_DAYS[f.date_preset]), None
    return None, None


def scope_conditions(user: User, f: SearchFilters, now: datetime) -> list:
    conds = [accessible_meeting_clause(user)]
    start, end = date_range(f, now)
    if start:
        conds.append(Meeting.start_at >= start)
    if end:
        conds.append(Meeting.start_at < end)
    if f.owner:
        conds.append(func.lower(Meeting.owner_key) == f.owner.strip().lower())
    if f.title:
        conds.append(Meeting.subject.ilike(_like(f.title.strip()), escape="\\"))
    if f.min_duration_min is not None:
        conds.append(Meeting.duration_sec >= f.min_duration_min * 60)
    if f.max_duration_min is not None:
        conds.append(Meeting.duration_sec <= f.max_duration_min * 60)
    if f.has_recording is not None:
        conds.append(Meeting.has_recording.is_(f.has_recording))
    if f.has_transcript is not None:
        conds.append(Meeting.has_transcript.is_(f.has_transcript))
    for pid in sorted(set(f.participant_ids)):  # every selected participant must have attended
        conds.append(exists().where(MP.meeting_id == Meeting.id, MP.participant_id == pid))
    if f.speaker_ids:
        conds.append(exists().where(MP.meeting_id == Meeting.id, MP.participant_id.in_(f.speaker_ids)))
    return conds


def tsquery(q: str, mode: str):
    """Strict AND for keyword mode / short queries; OR of the terms for longer natural-language queries in auto mode
    (ranking still favours passages that match more of the words)."""
    strict = func.websearch_to_tsquery("english", q)
    if mode == "auto" and len(q.split()) >= 3 and '"' not in q:
        return func.to_tsquery("english", func.replace(func.cast(strict, Text), " & ", " | "))
    return strict


def _keyword_list(db: Session, tsq, scope, speakers: list[int]) -> list[int]:
    rank = func.ts_rank_cd(TS.tsv, tsq)
    stmt = select(TS.id).where(TS.tsv.op("@@")(tsq), TS.meeting_id.in_(scope))
    if speakers:
        stmt = stmt.where(TS.participant_id.in_(speakers))
    return list(db.scalars(stmt.order_by(rank.desc(), TS.id).limit(CANDIDATES)))


def _semantic_list(db: Session, qvec: list[float], scope, speakers: list[int]) -> list[int]:
    db.execute(text(f"SET LOCAL hnsw.ef_search = {CANDIDATES}"))
    db.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    dist = TS.embedding.cosine_distance(qvec)
    stmt = select(TS.id, dist.label("d")).where(TS.embedding.is_not(None), TS.meeting_id.in_(scope))
    if speakers:
        stmt = stmt.where(TS.participant_id.in_(speakers))
    rows = db.execute(stmt.order_by(dist).limit(CANDIDATES)).all()
    max_d = get_settings().semantic_max_distance
    return [r.id for r in sorted(rows, key=lambda r: r.d) if r.d is not None and r.d <= max_d]


def _metadata_list(db: Session, q: str, scope) -> list[uuid.UUID]:
    like = _like(q)
    person = (
        select(MP.meeting_id.label("mid"),
               func.max(func.greatest(
                   func.similarity(P.name, q),
                   case((or_(P.name.ilike(like, escape="\\"), P.email.ilike(like, escape="\\")), 0.85), else_=0.0),
               )).label("ps"))
        .join(P, P.id == MP.participant_id)
        .where(or_(P.name.ilike(like, escape="\\"), P.email.ilike(like, escape="\\"), func.similarity(P.name, q) > 0.4))
        .group_by(MP.meeting_id)
        .subquery()
    )
    try:
        qid = uuid.UUID(q.strip())
    except ValueError:
        qid = None
    id_match = Meeting.id == qid if qid else literal(False)
    subject_like = Meeting.subject.ilike(like, escape="\\")
    score = func.greatest(
        case((id_match, 1.0), else_=0.0),
        case((subject_like, 0.9), else_=0.0),
        func.similarity(Meeting.subject, q),
        func.coalesce(person.c.ps, 0.0),
    )
    stmt = (
        select(Meeting.id)
        .outerjoin(person, person.c.mid == Meeting.id)
        .where(Meeting.id.in_(scope), or_(id_match, subject_like, func.similarity(Meeting.subject, q) > 0.3,
                                          person.c.mid.is_not(None)))
        .order_by(score.desc(), Meeting.start_at.desc().nulls_last())
        .limit(METADATA_CANDIDATES)
    )
    return list(db.scalars(stmt))


def _highlights(db: Session, tsq, seg_ids: list[int]) -> dict[int, list[tuple[int, int]]]:
    if not seg_ids:
        return {}
    opts = f'StartSel="{HL_START}", StopSel="{HL_STOP}", HighlightAll=true'
    rows = db.execute(
        select(TS.id, TS.text, func.ts_headline("english", TS.text, tsq, opts))
        .where(TS.id.in_(seg_ids))
    ).all()
    out = {}
    for sid, original, marked in rows:
        plain, ranges, i = [], [], 0
        pos = 0
        while i < len(marked):
            if marked.startswith(HL_START, i):
                j = marked.find(HL_STOP, i)
                if j < 0:
                    break
                word = marked[i + len(HL_START):j]
                ranges.append((pos, pos + len(word)))
                plain.append(word)
                pos += len(word)
                i = j + len(HL_STOP)
            else:
                plain.append(marked[i])
                pos += 1
                i += 1
        out[sid] = ranges if "".join(plain) == original else []
    return out


def _record_history(db: Session, user: User, req: SearchRequest, total: int) -> None:
    if req.page != 1 or (not req.q.strip() and req.filters.is_empty()):
        return
    db.add(SearchHistory(user_id=user.id, query=req.q.strip(), filters=req.filters.model_dump(mode="json",
                         exclude_defaults=True), mode=req.mode, result_count=total))
    db.commit()


def _order_meetings(db: Session, ids: list[uuid.UUID], scores: dict[uuid.UUID, float], sort: str) -> list[uuid.UUID]:
    info = {r.id: r for r in db.execute(select(Meeting.id, Meeting.start_at, Meeting.duration_sec)
                                       .where(Meeting.id.in_(ids)))}
    far_past = datetime.min.replace(tzinfo=UTC)

    def start(i):
        return info[i].start_at or far_past

    if sort == "date_asc":
        return sorted(ids, key=lambda i: (info[i].start_at is None, start(i)))
    if sort == "date_desc":
        return sorted(ids, key=start, reverse=True)
    if sort == "duration_desc":
        return sorted(ids, key=lambda i: info[i].duration_sec or 0, reverse=True)
    return sorted(ids, key=lambda i: (scores.get(i, 0.0), start(i)), reverse=True)


def search(db: Session, user: User, req: SearchRequest, embedder=None) -> SearchResponse:
    t0 = time.perf_counter()
    now = datetime.now(UTC)
    q = req.q.strip()
    scope = select(Meeting.id).where(*scope_conditions(user, req.filters, now))
    offset = (req.page - 1) * req.page_size

    if not q:
        order = {
            "date_asc": (Meeting.start_at.asc().nulls_last(),),
            "duration_desc": (Meeting.duration_sec.desc().nulls_last(),),
        }.get(req.sort, (Meeting.start_at.desc().nulls_last(),))
        total = db.scalar(select(func.count()).select_from(scope.subquery()))
        ids = list(db.scalars(select(Meeting.id).where(Meeting.id.in_(scope)).order_by(*order, Meeting.id)
                              .offset(offset).limit(req.page_size)))
        summaries = build_summaries(db, ids)
        _record_history(db, user, req, total)
        return SearchResponse(total=total, page=req.page, page_size=req.page_size, semantic_used=False,
                              took_ms=int((time.perf_counter() - t0) * 1000),
                              results=[MeetingHit(meeting=summaries[i], score=0.0, match_types=[], matches=[])
                                       for i in ids])

    speakers = req.filters.speaker_ids
    tsq = tsquery(q, req.mode)
    kw_ids = [] if req.mode == "semantic" else _keyword_list(db, tsq, scope, speakers)
    sem_ids: list[int] = []
    semantic_used = False
    wants_semantic = req.mode == "semantic" or (req.mode == "auto" and len(q.split()) >= 2)
    if embedder is not None and wants_semantic:
        try:
            qvec = embedder.embed_query(q)
            sem_ids = _semantic_list(db, qvec, scope, speakers)
            semantic_used = True
        except Exception:
            db.rollback()
            log.warning("semantic search unavailable; using keyword results only", exc_info=True)
    meta_ids = _metadata_list(db, q, scope)

    seg_score: dict[int, float] = defaultdict(float)
    seg_types: dict[int, set[str]] = defaultdict(set)
    for name, lst in (("keyword", kw_ids), ("semantic", sem_ids)):
        for rank, sid in enumerate(lst, 1):
            seg_score[sid] += 1.0 / (RRF_K + rank)
            seg_types[sid].add(name)

    seg_rows = {}
    if seg_score:
        seg_rows = {r.id: r for r in db.execute(
            select(TS.id, TS.meeting_id, TS.kind, TS.speaker_name, TS.section, TS.start_sec, TS.text)
            .where(TS.id.in_(list(seg_score))))}

    by_meeting: dict[uuid.UUID, list[int]] = defaultdict(list)
    for sid in sorted(seg_score, key=lambda s: seg_score[s], reverse=True):
        if sid in seg_rows:
            by_meeting[seg_rows[sid].meeting_id].append(sid)

    m_score: dict[uuid.UUID, float] = {mid: sum(seg_score[s] for s in sids[:MATCHES_PER_MEETING])
                                       for mid, sids in by_meeting.items()}
    m_types: dict[uuid.UUID, set[str]] = defaultdict(set)
    for mid, sids in by_meeting.items():
        for s in sids[:MATCHES_PER_MEETING]:
            m_types[mid] |= seg_types[s]
    for rank, mid in enumerate(meta_ids, 1):
        m_score[mid] = m_score.get(mid, 0.0) + METADATA_WEIGHT / (RRF_K + rank)
        m_types[mid].add("metadata")

    ordered = _order_meetings(db, list(m_score), m_score, req.sort)
    page_ids = ordered[offset: offset + req.page_size]
    summaries = build_summaries(db, page_ids)

    page_kw = [s for mid in page_ids for s in by_meeting.get(mid, [])[:MATCHES_PER_MEETING] if "keyword" in seg_types[s]]
    hl = _highlights(db, tsq, page_kw)

    results = []
    for mid in page_ids:
        matches = []
        for sid in by_meeting.get(mid, [])[:MATCHES_PER_MEETING]:
            r, types = seg_rows[sid], seg_types[sid]
            mt = "both" if len(types) == 2 else next(iter(types))
            ranges = hl.get(sid, []) if "keyword" in types else []
            if not ranges and "semantic" in types:
                ranges = [(0, len(r.text))]
            matches.append(SegmentMatch(
                segment_id=sid, kind=r.kind, speaker_name=r.speaker_name, section=r.section,
                start_sec=float(r.start_sec) if r.start_sec is not None else None, text=r.text,
                highlights=ranges, match_type=mt,
            ))
        results.append(MeetingHit(meeting=summaries[mid], score=round(m_score[mid], 6),
                                  match_types=sorted(m_types[mid]), matches=matches))

    total = len(ordered)
    _record_history(db, user, req, total)
    took = int((time.perf_counter() - t0) * 1000)
    log.info("search", extra={"q_len": len(q), "mode": req.mode, "total": total, "took_ms": took,
                              "semantic_used": semantic_used})
    return SearchResponse(total=total, page=req.page, page_size=req.page_size, results=results, took_ms=took,
                          semantic_used=semantic_used)


def suggest(db: Session, user: User, q: str) -> dict:
    q = (q or "").strip()[:200]
    recent_q = (
        select(SearchHistory.query, func.max(SearchHistory.created_at).label("t"))
        .where(SearchHistory.user_id == user.id, SearchHistory.query != "")
        .group_by(SearchHistory.query)
        .order_by(func.max(SearchHistory.created_at).desc())
        .limit(5)
    )
    if q:
        recent_q = recent_q.where(SearchHistory.query.ilike(q.replace("%", "\\%").replace("_", "\\_") + "%",
                                                            escape="\\"))
    recent = [r.query for r in db.execute(recent_q)]
    if not q:
        return {"participants": [], "meetings": [], "recent": recent}

    like = _like(q)
    visible = select(Meeting.id).where(accessible_meeting_clause(user))
    people = db.execute(
        select(P.id, P.name, P.email, P.is_internal)
        .where(or_(P.name.ilike(like, escape="\\"), P.email.ilike(like, escape="\\"), func.similarity(P.name, q) > 0.3),
               exists().where(MP.participant_id == P.id, MP.meeting_id.in_(visible)))
        .order_by(func.similarity(P.name, q).desc(), P.name)
        .limit(5)
    ).all()
    meetings = db.execute(
        select(Meeting.id, Meeting.subject, Meeting.start_at)
        .where(Meeting.id.in_(visible), Meeting.subject.ilike(like, escape="\\"))
        .order_by(Meeting.start_at.desc().nulls_last())
        .limit(5)
    ).all()
    return {
        "participants": [{"id": p.id, "name": p.name, "email": p.email, "is_internal": p.is_internal} for p in people],
        "meetings": [{"id": str(m.id), "subject": m.subject, "start_at": _iso_z(m.start_at) if m.start_at else None}
                     for m in meetings],
        "recent": recent,
    }
