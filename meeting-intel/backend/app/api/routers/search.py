from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.embeddings import get_query_embedder
from app.api.schemas import _iso_z
from app.auth.deps import current_user
from app.db import get_db
from app.models import SearchHistory, User
from app.search.schemas import SearchRequest, SearchResponse
from app.search.service import search, suggest

router = APIRouter(prefix="/api/search", tags=["search"])


@router.post("", response_model=SearchResponse)
def search_meetings(
    req: SearchRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    embedder=Depends(get_query_embedder),
) -> SearchResponse:
    return search(db, user, req, embedder)


@router.get("/suggest")
def search_suggest(q: str = Query("", max_length=200), user: User = Depends(current_user),
                   db: Session = Depends(get_db)) -> dict:
    return suggest(db, user, q)


@router.get("/history")
def search_history(limit: int = Query(20, ge=1, le=100), user: User = Depends(current_user),
                   db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(
        select(SearchHistory).where(SearchHistory.user_id == user.id)
        .order_by(SearchHistory.created_at.desc(), SearchHistory.id.desc()).limit(limit)
    )
    return [{"id": h.id, "query": h.query, "filters": h.filters, "mode": h.mode, "result_count": h.result_count,
             "created_at": _iso_z(h.created_at)} for h in rows]
