"""Bing の API キーの表と、接続設定がどのキーを使うか

Bing のキーは顧客ごとに複数持ち、サイトごとにどれを使うか選ぶ（data_sources.md §4、2026-11-27 利用者の決定）。
接続設定にキーを持たせる列（credentials_encrypted）は使わなくなったので消す（まだ何も入っていない）。

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bing_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("key_encrypted", sa.Text(), nullable=False),
        sa.Column("last4", sa.String(4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "name"),
    )
    op.create_index("ix_bing_keys_tenant_id", "bing_keys", ["tenant_id"])
    op.add_column("connections", sa.Column("bing_key_id", sa.Integer(), sa.ForeignKey("bing_keys.id")))
    op.drop_column("connections", "credentials_encrypted")


def downgrade() -> None:
    op.add_column("connections", sa.Column("credentials_encrypted", sa.Text()))
    op.drop_column("connections", "bing_key_id")
    op.drop_index("ix_bing_keys_tenant_id", table_name="bing_keys")
    op.drop_table("bing_keys")
