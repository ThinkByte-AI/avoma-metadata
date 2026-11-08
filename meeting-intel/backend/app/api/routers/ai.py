from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai.assistant import AskRequest, AskResponse, ask
from app.ai.chat import get_chat_model
from app.ai.embeddings import get_query_embedder
from app.auth.deps import current_user
from app.db import get_db
from app.models import User

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/ask", response_model=AskResponse)
def ask_question(
    req: AskRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    embedder=Depends(get_query_embedder),
    chat=Depends(get_chat_model),
) -> AskResponse:
    return ask(db, user, req, embedder, chat)
