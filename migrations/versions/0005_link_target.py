"""紐づけ先を接続設定に持つ・取得ログに取った先を持つ（コードレビューの対応。2026-11-28）

- 紐づけ先（Search Console・Bing のサイトの URL）を sites の2列から connections.target に移す。
  紐づけているかどうかと紐づけ先を、1か所（connections の行）で持つため。
- sync_runs.target: 取った先。紐づけ先を変えたら、前の先の数字を消して取り直すのに使う。
- users.tenant_id に索引。connections.bing_key_id は、使っているキーを消せない（RESTRICT）と明示する。

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("connections", sa.Column("target", sa.Text()))
    op.execute("UPDATE connections c SET target = s.gsc_site_url FROM sites s WHERE c.site_id = s.id AND c.source = 'gsc'")
    op.execute("UPDATE connections c SET target = s.bing_site_url FROM sites s WHERE c.site_id = s.id AND c.source = 'bing'")
    # 紐づけ先の無い Search Console・Bing の接続（食い違い）は、紐づけていないのと同じなので消す
    op.execute("DELETE FROM connections WHERE source IN ('gsc', 'bing') AND target IS NULL")
    op.create_check_constraint("ck_connections_target", "connections", "source = 'ga4' OR target IS NOT NULL")
    op.drop_column("sites", "gsc_site_url")
    op.drop_column("sites", "bing_site_url")

    op.add_column("sync_runs", sa.Column("target", sa.Text()))
    # これまでの取得は、今の紐づけ先から取った（紐づけ先を変えたことはまだ無い）
    op.execute(
        "UPDATE sync_runs r SET target = c.target FROM connections c WHERE r.site_id = c.site_id AND r.source = c.source"
    )

    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])
    op.drop_constraint("connections_bing_key_id_fkey", "connections", type_="foreignkey")
    op.create_foreign_key(
        "connections_bing_key_id_fkey", "connections", "bing_keys", ["bing_key_id"], ["id"], ondelete="RESTRICT"
    )


def downgrade() -> None:
    op.drop_constraint("connections_bing_key_id_fkey", "connections", type_="foreignkey")
    op.create_foreign_key("connections_bing_key_id_fkey", "connections", "bing_keys", ["bing_key_id"], ["id"])
    op.drop_index("ix_users_tenant_id", table_name="users")
    op.drop_column("sync_runs", "target")
    op.add_column("sites", sa.Column("gsc_site_url", sa.Text()))
    op.add_column("sites", sa.Column("bing_site_url", sa.Text()))
    op.execute("UPDATE sites s SET gsc_site_url = c.target FROM connections c WHERE c.site_id = s.id AND c.source = 'gsc'")
    op.execute("UPDATE sites s SET bing_site_url = c.target FROM connections c WHERE c.site_id = s.id AND c.source = 'bing'")
    op.drop_constraint("ck_connections_target", "connections", type_="check")
    op.drop_column("connections", "target")
