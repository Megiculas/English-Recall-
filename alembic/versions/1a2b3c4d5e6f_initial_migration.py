"""Initial migration

Revision ID: 1a2b3c4d5e6f
Revises: 
Create Date: 2024-03-05 09:48:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1a2b3c4d5e6f'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('users',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('words',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('word', sa.String(), nullable=False),
    sa.Column('context_given', sa.Text(), nullable=True),
    sa.Column('llm_response', sa.Text(), nullable=True),
    sa.Column('level', sa.Integer(), nullable=False),
    sa.Column('next_review', sa.DateTime(timezone=True), nullable=False),
    sa.Column('is_learned', sa.Boolean(), nullable=False),
    sa.Column('is_waiting_for_review', sa.Boolean(), nullable=False, server_default=sa.text('FALSE')),
    sa.Column('added_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_words_user_id'), 'words', ['user_id'], unique=False)
    op.create_index(op.f('ix_words_word'), 'words', ['word'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_words_word'), table_name='words')
    op.drop_index(op.f('ix_words_user_id'), table_name='words')
    op.drop_table('words')
    op.drop_table('users')
