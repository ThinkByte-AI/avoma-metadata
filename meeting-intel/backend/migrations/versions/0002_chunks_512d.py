"""conversation chunks for semantic search; 512-dimension embeddings

Semantic search now embeds ~150-word conversation windows (kind='chunk') instead of single
utterances, at 512 dimensions. Existing embeddings are dropped and parsed/indexed meetings are
sent back to 'discovered' so the next ingestion run rebuilds their segments and vectors.

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _swap_vector_dim(dim: int) -> None:
    op.drop_index("ix_segments_embedding_hnsw", table_name="transcript_segments")
    op.execute("UPDATE transcript_segments SET embedding = NULL WHERE embedding IS NOT NULL")
    op.execute(f"ALTER TABLE transcript_segments ALTER COLUMN embedding TYPE vector({dim}) USING NULL")
    op.create_index(
        "ix_segments_embedding_hnsw", "transcript_segments", ["embedding"], unique=False,
        postgresql_using="hnsw", postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def upgrade() -> None:
    op.drop_constraint("ck_segments_kind", "transcript_segments", type_="check")
    op.create_check_constraint("ck_segments_kind", "transcript_segments", "kind IN ('utterance','note','chunk')")
    op.add_column("transcript_segments", sa.Column("participant_ids", postgresql.ARRAY(sa.Integer()), nullable=True))
    _swap_vector_dim(512)
    op.execute("UPDATE meetings SET ingest_status = 'discovered', indexed_at = NULL "
               "WHERE ingest_status IN ('parsed', 'indexed')")


def downgrade() -> None:
    op.execute("DELETE FROM transcript_segments WHERE kind = 'chunk'")
    _swap_vector_dim(1024)
    op.drop_column("transcript_segments", "participant_ids")
    op.drop_constraint("ck_segments_kind", "transcript_segments", type_="check")
    op.create_check_constraint("ck_segments_kind", "transcript_segments", "kind IN ('utterance','note')")
    op.execute("UPDATE meetings SET ingest_status = 'discovered', indexed_at = NULL "
               "WHERE ingest_status IN ('parsed', 'indexed')")
