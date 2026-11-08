from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.deps import require_admin
from app.aws.s3 import S3Store, get_store
from app.config import get_settings
from app.db import get_db
from app.models import User

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/status")
def system_status(
    _: User = Depends(require_admin), store: S3Store = Depends(get_store), db: Session = Depends(get_db)
) -> dict:
    s = get_settings()
    try:
        db.execute(text("SELECT 1"))
        db_state = "ok"
    except Exception:
        db_state = "error"
    return {
        "aws": store.check(),
        "bucket": s.s3_bucket,
        "prefixes": s.s3_prefix_list,
        "region": s.aws_region,
        "embed_model": s.bedrock_embed_model,
        "chat_model": s.bedrock_chat_model,
        "app_mode": s.app_mode,
        "db": db_state,
    }
