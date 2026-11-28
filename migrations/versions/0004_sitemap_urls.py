"""サイトマップに載っている URL（インデックスの目安に使う。screen_design.md §7）

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sitemap_urls",
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("path", sa.Text(), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("sitemap_urls")
