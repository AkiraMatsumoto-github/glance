"""Search Console・Bing の取り込みの表と取得ログ（database_design.md §2・§4・§5）

どのデータの表も、サイトを削除したら一緒に消す（2026-11-27 利用者の決定）。

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _site_id() -> sa.Column:
    return sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="CASCADE"), primary_key=True)


def _gsc_metrics() -> list[sa.Column]:
    return [
        sa.Column("clicks", sa.Integer(), nullable=False),
        sa.Column("impressions", sa.Integer(), nullable=False),
        sa.Column("position", sa.Float(), nullable=False),
        sa.Column("position_weighted", sa.Float(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "sync_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("table_name", sa.String(64), nullable=False),
        sa.Column("start_date", sa.Date()),
        sa.Column("end_date", sa.Date()),
        sa.Column("rows", sa.Integer(), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sync_runs_site_id", "sync_runs", ["site_id"])
    op.create_table(
        "gsc_site",
        _site_id(),
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("country", sa.String(16), primary_key=True),
        sa.Column("device", sa.String(16), primary_key=True),
        *_gsc_metrics(),
    )
    op.create_table(
        "gsc_page",
        _site_id(),
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("page", sa.Text(), primary_key=True),
        sa.Column("device", sa.String(16), primary_key=True),
        *_gsc_metrics(),
    )
    op.create_table(
        "gsc_query_page",
        _site_id(),
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("query", sa.Text(), primary_key=True),
        sa.Column("page", sa.Text(), primary_key=True),
        *_gsc_metrics(),
    )
    op.create_table(
        "bing_site_daily",
        _site_id(),
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("clicks", sa.Integer(), nullable=False),
        sa.Column("impressions", sa.Integer(), nullable=False),
        sa.Column("raw", JSONB(), nullable=False),
    )
    op.create_table(
        "bing_page_weekly",
        _site_id(),
        sa.Column("week", sa.Date(), primary_key=True),
        sa.Column("page", sa.Text(), primary_key=True),
        sa.Column("clicks", sa.Integer(), nullable=False),
        sa.Column("impressions", sa.Integer(), nullable=False),
        sa.Column("position", sa.Float()),
        sa.Column("raw", JSONB(), nullable=False),
    )
    op.create_table(
        "bing_crawl_daily",
        _site_id(),
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("crawled", sa.Integer(), nullable=False),
        sa.Column("indexed", sa.Integer(), nullable=False),
        sa.Column("backlinks", sa.Integer(), nullable=False),
        sa.Column("crawl_errors", sa.Integer(), nullable=False),
        sa.Column("raw", JSONB(), nullable=False),
    )


def downgrade() -> None:
    for table in ["bing_crawl_daily", "bing_page_weekly", "bing_site_daily", "gsc_query_page", "gsc_page", "gsc_site"]:
        op.drop_table(table)
    op.drop_index("ix_sync_runs_site_id", table_name="sync_runs")
    op.drop_table("sync_runs")
