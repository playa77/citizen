"""Add conversation, conversation_message, and conversation_document tables.

Revision ID: 003_add_conversations
Revises: 002_add_cache_entry
Create Date: 2026-05-08 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "003_add_conversations"
down_revision: Union[str, None] = "002_add_cache_entry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # conversation
    op.create_table(
        "conversation",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # conversation_message
    op.create_table(
        "conversation_message",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversation.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.String(20),
            nullable=False,
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_message_conversation",
        "conversation_message",
        ["conversation_id"],
    )

    # conversation_document
    op.create_table(
        "conversation_document",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversation.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("normalized_text", sa.Text, nullable=False),
        sa.Column(
            "case_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("case_run.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_document_conversation",
        "conversation_document",
        ["conversation_id"],
    )

    # Allow conversation_document to reference case_run
    op.create_check_constraint(
        "ck_conversation_message_role",
        "conversation_message",
        "role IN ('user', 'assistant', 'system')",
    )


def downgrade() -> None:
    op.drop_index("idx_document_conversation", table_name="conversation_document")
    op.drop_table("conversation_document")
    op.drop_index("idx_message_conversation", table_name="conversation_message")
    op.drop_table("conversation_message")
    op.drop_table("conversation")
