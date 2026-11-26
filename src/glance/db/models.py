"""テーブルの定義（database_design.md §2。1番目の段階で作る5つ）。"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    """顧客。1番目の段階では自社の1つだけ（マイグレーションで作る）。"""

    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    """利用者。Google でログインした人（technical_design.md §4）。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    google_sub: Mapped[str] = mapped_column(String(255), unique=True)
    email: Mapped[str] = mapped_column(String(320))
    # 更新トークン（Fernet で暗号化したもの）。2番目の段階で Google ログインをつないでから入る
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text)
    scopes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LoginSession(Base):
    """ログインのセッション。ID そのものは持たず、ハッシュだけを持つ。"""

    __tablename__ = "sessions"

    id_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Site(Base):
    """サイト。並び順はリアルタイムの表・グラフの色の順になる。"""

    __tablename__ = "sites"
    __table_args__ = (UniqueConstraint("tenant_id", "ga4_property_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    sort_order: Mapped[int] = mapped_column(Integer)
    timezone: Mapped[str] = mapped_column(String(64))
    ga4_property_id: Mapped[str | None] = mapped_column(String(32))
    gsc_site_url: Mapped[str | None] = mapped_column(Text)
    bing_site_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Connection(Base):
    """データ接続。Google ログインのときは、どの利用者の更新トークンで API を呼ぶかを持つ。"""

    __tablename__ = "connections"
    __table_args__ = (UniqueConstraint("site_id", "source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(16))  # ga4 / gsc / bing
    auth_method: Mapped[str] = mapped_column(String(16))  # google / api_key
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    credentials_encrypted: Mapped[str | None] = mapped_column(Text)  # Bing の API キーなど
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
