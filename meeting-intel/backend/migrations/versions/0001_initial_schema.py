"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-11-08 12:13:17.744615
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import pgvector.sqlalchemy

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table('meetings',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('subject', sa.Text(), nullable=False),
    sa.Column('start_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('duration_sec', sa.Integer(), nullable=True),
    sa.Column('owner_key', sa.Text(), nullable=True),
    sa.Column('accounts', postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('s3_folder', sa.Text(), nullable=False),
    sa.Column('has_recording', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('has_transcript', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('has_notes', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('notes_md', sa.Text(), nullable=True),
    sa.Column('topics', postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('transcription_uuid', sa.UUID(), nullable=True),
    sa.Column('duplicate_of', sa.UUID(), nullable=True),
    sa.Column('ingest_status', sa.Text(), server_default='discovered', nullable=False),
    sa.Column('ingest_error', sa.Text(), nullable=True),
    sa.Column('ingest_attempts', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('transcript_etag', sa.Text(), nullable=True),
    sa.Column('notes_etag', sa.Text(), nullable=True),
    sa.Column('parsed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('indexed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("ingest_status IN ('discovered','parsed','indexed','failed','skipped')", name='ck_meetings_ingest_status'),
    sa.ForeignKeyConstraint(['duplicate_of'], ['meetings.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_meetings_accounts', 'meetings', ['accounts'], unique=False, postgresql_using='gin')
    op.create_index('ix_meetings_ingest_status', 'meetings', ['ingest_status'], unique=False)
    op.create_index('ix_meetings_start_at', 'meetings', ['start_at'], unique=False)
    op.create_index('ix_meetings_subject_trgm', 'meetings', ['subject'], unique=False, postgresql_using='gin', postgresql_ops={'subject': 'gin_trgm_ops'})
    op.create_table('participants',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('email', sa.Text(), nullable=True),
    sa.Column('is_internal', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('normalized_key', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('normalized_key')
    )
    op.create_index('ix_participants_email_trgm', 'participants', ['email'], unique=False, postgresql_using='gin', postgresql_ops={'email': 'gin_trgm_ops'})
    op.create_index('ix_participants_name_trgm', 'participants', ['name'], unique=False, postgresql_using='gin', postgresql_ops={'name': 'gin_trgm_ops'})
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.Text(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=False),
    sa.Column('role', sa.Text(), server_default='user', nullable=False),
    sa.Column('access_scope', sa.Text(), server_default='own', nullable=False),
    sa.Column('account_label', sa.Text(), nullable=True),
    sa.Column('can_download', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("access_scope IN ('own','all')", name='ck_users_access_scope'),
    sa.CheckConstraint("role IN ('admin','user')", name='ck_users_role'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('audit_logs',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('action', sa.Text(), nullable=False),
    sa.Column('target_type', sa.Text(), nullable=True),
    sa.Column('target_id', sa.Text(), nullable=True),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('ip', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'], unique=False)
    op.create_table('ingestion_jobs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), server_default='queued', nullable=False),
    sa.Column('requested_by', sa.Integer(), nullable=True),
    sa.Column('stats', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("kind IN ('initial','sync','retry')", name='ck_jobs_kind'),
    sa.CheckConstraint("status IN ('queued','running','paused','completed','failed','cancelled')", name='ck_jobs_status'),
    sa.ForeignKeyConstraint(['requested_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('uq_jobs_one_active', 'ingestion_jobs', [sa.literal_column('(true)')], unique=True, postgresql_where=sa.text("status IN ('queued','running','paused')"))
    op.create_table('meeting_participants',
    sa.Column('meeting_id', sa.UUID(), nullable=False),
    sa.Column('participant_id', sa.Integer(), nullable=False),
    sa.Column('speaker_id', sa.Integer(), nullable=True),
    sa.Column('speaking_sec', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False),
    sa.Column('is_internal', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.ForeignKeyConstraint(['meeting_id'], ['meetings.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['participant_id'], ['participants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('meeting_id', 'participant_id')
    )
    op.create_index('ix_meeting_participants_participant_id', 'meeting_participants', ['participant_id'], unique=False)
    op.create_table('recordings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('meeting_id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('s3_key', sa.Text(), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('storage_class', sa.Text(), nullable=True),
    sa.Column('etag', sa.Text(), nullable=True),
    sa.Column('content_type', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind IN ('audio','video')", name='ck_recordings_kind'),
    sa.ForeignKeyConstraint(['meeting_id'], ['meetings.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('meeting_id', 'kind', name='uq_recordings_meeting_kind'),
    sa.UniqueConstraint('s3_key')
    )
    op.create_table('search_history',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('query', sa.Text(), server_default='', nullable=False),
    sa.Column('filters', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('mode', sa.Text(), server_default='auto', nullable=False),
    sa.Column('result_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_search_history_user_created', 'search_history', ['user_id', sa.literal_column('created_at DESC')], unique=False)
    op.create_table('transcripts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('meeting_id', sa.UUID(), nullable=False),
    sa.Column('s3_key', sa.Text(), nullable=False),
    sa.Column('transcription_uuid', sa.UUID(), nullable=True),
    sa.Column('etag', sa.Text(), nullable=True),
    sa.Column('segment_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('word_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('speaker_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('last_word_sec', sa.Numeric(precision=12, scale=3), server_default=sa.text('0'), nullable=False),
    sa.Column('source_modified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['meeting_id'], ['meetings.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('meeting_id')
    )
    op.create_table('transcript_segments',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('meeting_id', sa.UUID(), nullable=False),
    sa.Column('transcript_id', sa.Integer(), nullable=True),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('seq', sa.Integer(), nullable=False),
    sa.Column('participant_id', sa.Integer(), nullable=True),
    sa.Column('speaker_name', sa.Text(), nullable=True),
    sa.Column('section', sa.Text(), nullable=True),
    sa.Column('start_sec', sa.Numeric(precision=12, scale=3), nullable=True),
    sa.Column('end_sec', sa.Numeric(precision=12, scale=3), nullable=True),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('tsv', postgresql.TSVECTOR(), sa.Computed("to_tsvector('english', text)", persisted=True), nullable=True),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=1024), nullable=True),
    sa.CheckConstraint("kind IN ('utterance','note')", name='ck_segments_kind'),
    sa.ForeignKeyConstraint(['meeting_id'], ['meetings.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['participant_id'], ['participants.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['transcript_id'], ['transcripts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('meeting_id', 'kind', 'seq', name='uq_segments_meeting_kind_seq')
    )
    op.create_index('ix_segments_embedding_hnsw', 'transcript_segments', ['embedding'], unique=False, postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64}, postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.create_index('ix_segments_meeting_start', 'transcript_segments', ['meeting_id', 'start_sec'], unique=False)
    op.create_index('ix_segments_participant_id', 'transcript_segments', ['participant_id'], unique=False)
    op.create_index('ix_segments_tsv', 'transcript_segments', ['tsv'], unique=False, postgresql_using='gin')


def downgrade() -> None:
    op.drop_index('ix_segments_tsv', table_name='transcript_segments', postgresql_using='gin')
    op.drop_index('ix_segments_participant_id', table_name='transcript_segments')
    op.drop_index('ix_segments_meeting_start', table_name='transcript_segments')
    op.drop_index('ix_segments_embedding_hnsw', table_name='transcript_segments', postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64}, postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.drop_table('transcript_segments')
    op.drop_table('transcripts')
    op.drop_index('ix_search_history_user_created', table_name='search_history')
    op.drop_table('search_history')
    op.drop_table('recordings')
    op.drop_index('ix_meeting_participants_participant_id', table_name='meeting_participants')
    op.drop_table('meeting_participants')
    op.drop_index('uq_jobs_one_active', table_name='ingestion_jobs', postgresql_where=sa.text("status IN ('queued','running','paused')"))
    op.drop_table('ingestion_jobs')
    op.drop_index('ix_audit_logs_created_at', table_name='audit_logs')
    op.drop_table('audit_logs')
    op.drop_table('users')
    op.drop_index('ix_participants_name_trgm', table_name='participants', postgresql_using='gin', postgresql_ops={'name': 'gin_trgm_ops'})
    op.drop_index('ix_participants_email_trgm', table_name='participants', postgresql_using='gin', postgresql_ops={'email': 'gin_trgm_ops'})
    op.drop_table('participants')
    op.drop_index('ix_meetings_subject_trgm', table_name='meetings', postgresql_using='gin', postgresql_ops={'subject': 'gin_trgm_ops'})
    op.drop_index('ix_meetings_start_at', table_name='meetings')
    op.drop_index('ix_meetings_ingest_status', table_name='meetings')
    op.drop_index('ix_meetings_accounts', table_name='meetings', postgresql_using='gin')
    op.drop_table('meetings')
