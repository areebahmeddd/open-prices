"""Add user is_moderator field

Revision ID: 7ac630e20d66
Revises: f3c157567667
Create Date: 2024-02-06 01:05:59.414434

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7ac630e20d66"
down_revision: Union[str, None] = "f3c157567667"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "users",
        sa.Column("is_moderator", sa.Boolean(), server_default="false", nullable=False),
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("users", "is_moderator")
    # ### end Alembic commands ###
