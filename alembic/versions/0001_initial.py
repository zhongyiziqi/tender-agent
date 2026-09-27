"""Initial tender agent schema.

Revision ID: 0001_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_documents_sha256", "documents", ["sha256"])
    op.create_table(
        "source_chunks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("section", sa.String(255)),
        sa.Column("page_number", sa.Integer()),
        sa.Column("content", sa.Text(), nullable=False),
    )
    op.create_index("ix_source_chunks_document_id", "source_chunks", ["document_id"])
    op.create_table(
        "agent_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("input_json", sa.Text(), nullable=False),
        sa.Column("output_json", sa.Text()),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_tasks_task_type", "agent_tasks", ["task_type"])
    op.create_index("ix_agent_tasks_status", "agent_tasks", ["status"])
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("agent_tasks.id"), nullable=False),
        sa.Column("node_name", sa.String(80), nullable=False),
        sa.Column("model_name", sa.String(128), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("sources_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_runs_task_id", "agent_runs", ["task_id"])
    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("agent_tasks.id"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_artifacts_task_id", "artifacts", ["task_id"])
    op.create_table(
        "review_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("agent_tasks.id"), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_review_items_task_id", "review_items", ["task_id"])
    op.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS source_chunks_fts "
        "USING fts5(content, section, document_id UNINDEXED)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS source_chunks_fts")
    op.drop_table("review_items")
    op.drop_table("artifacts")
    op.drop_table("agent_runs")
    op.drop_table("agent_tasks")
    op.drop_table("source_chunks")
    op.drop_table("documents")

