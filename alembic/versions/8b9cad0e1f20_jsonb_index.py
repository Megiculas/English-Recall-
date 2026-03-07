"""Update llm_response to JSONB and add composite index

Revision ID: 8b9cad0e1f20
Revises: 1a2b3c4d5e6f
Create Date: 2026-03-06 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '8b9cad0e1f20'
down_revision: Union[str, None] = '1a2b3c4d5e6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE words ALTER COLUMN llm_response TYPE JSONB USING llm_response::jsonb'
    )
    op.create_index('ix_word_user_word', 'words', ['user_id', 'word'], unique=False)
    op.create_unique_constraint('uq_word_user_word', 'words', ['user_id', 'word'])


def downgrade() -> None:
    op.drop_constraint('uq_word_user_word', 'words', type_='unique')
    op.drop_index('ix_word_user_word', table_name='words')
    op.execute(
        'ALTER TABLE words ALTER COLUMN llm_response TYPE TEXT USING llm_response::text'
    )
