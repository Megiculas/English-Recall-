"""Add learning funnel status and slots

Revision ID: e1f2g3h4i5j6
Revises: c0123d456e78
Create Date: 2026-03-10 14:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1f2g3h4i5j6'
down_revision: Union[str, None] = 'c0123d456e78'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update 'users' table
    op.add_column('users', sa.Column('active_slots_limit', sa.Integer(), server_default='10', nullable=False))
    op.add_column('users', sa.Column('batch_review_time', sa.Time(), server_default='19:00:00', nullable=False))
    
    # 2. Update 'words' table
    op.add_column('words', sa.Column('status', sa.String(), server_default='inbox', nullable=False))
    
    # Створюємо індекс для прискорення вибірки за статусом
    op.create_index('ix_word_user_status', 'words', ['user_id', 'status'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_word_user_status', table_name='words')
    op.drop_column('words', 'status')
    op.drop_column('users', 'batch_review_time')
    op.drop_column('users', 'active_slots_limit')
