"""Add user gamification fields

Revision ID: c0123d456e78
Revises: 8b9cad0e1f20
Create Date: 2026-03-06 15:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c0123d456e78'
down_revision: Union[str, None] = '8b9cad0e1f20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('last_activity', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('current_streak', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('max_streak', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('users', 'max_streak')
    op.drop_column('users', 'current_streak')
    op.drop_column('users', 'last_activity')
