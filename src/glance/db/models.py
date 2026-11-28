"""テーブルの定義（database_design.md §2）。"""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    """顧客（データを分ける単位）。いまは利用者1人に1つで、初めてログインしたときに作る（名前はその人のメールアドレス）。

    マイグレーションで作った「自社」には、この決まりの前からいた利用者が入っている（2026-11-28 利用者の決定）。
    """

    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    """利用者。Google でログインした人（technical_design.md §4）。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    google_sub: Mapped[str] = mapped_column(String(255), unique=True)
    email: Mapped[str] = mapped_column(String(320))
    # 更新トークン（Fernet で暗号化したもの）。Google でログインしたときに入る（フェイクのログインでは空）
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
    """サイト。並び順はリアルタイムの表・グラフの色の順になる。

    Search Console・Bing の紐づけ先は、接続設定（connections）の target に持つ。
    """

    __tablename__ = "sites"
    __table_args__ = (UniqueConstraint("tenant_id", "ga4_property_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    sort_order: Mapped[int] = mapped_column(Integer)
    timezone: Mapped[str] = mapped_column(String(64))
    ga4_property_id: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BingKey(Base):
    """Bing の API キー。顧客ごとに複数持て、サイトごとにどれを使うか選ぶ（data_sources.md §4）。

    キーそのものは画面に出さず、名前と末尾4文字だけを出す。
    """

    __tablename__ = "bing_keys"
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    key_encrypted: Mapped[str] = mapped_column(Text)  # Fernet で暗号化したもの
    last4: Mapped[str] = mapped_column(String(4))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Connection(Base):
    """データ接続。ソースごとに1行で、この行があれば紐づけている。紐づけを外すと消す。

    target は紐づけ先（Search Console・Bing のサイトの URL。GA4 はサイトのプロパティ ID を使うので空）。
    Google（GA4・Search Console）は、どの利用者の更新トークンで API を呼ぶかを持つ。
    Bing は、どのキーで API を呼ぶかを持つ（使っているキーは消せない）。
    """

    __tablename__ = "connections"
    __table_args__ = (
        UniqueConstraint("site_id", "source"),
        CheckConstraint("source = 'ga4' OR target IS NOT NULL", name="ck_connections_target"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(16))  # ga4 / gsc / bing
    auth_method: Mapped[str] = mapped_column(String(16))  # google / api_key
    target: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    bing_key_id: Mapped[int | None] = mapped_column(ForeignKey("bing_keys.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --- 取り込み（data_sources.md §1・§3・§4、database_design.md §4・§5） ---------------------------
# どのデータの表も、サイトを削除したら一緒に消す（database_design.md §2）。紐づけを外しても消さない


def _site_fk() -> Mapped[int]:
    return mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), primary_key=True)


class SyncRun(Base):
    """取得ログ。サイト・ソース・表・対象期間・行数・成否。画面の「◯月◯日までのデータ」と、次に取る範囲に使う。"""

    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(16))  # gsc / bing
    table_name: Mapped[str] = mapped_column(String(64))
    # 取った先（Search Console・Bing のサイトの URL）。紐づけ先を変えたら、前の先の数字を消して取り直すのに使う
    target: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    rows: Mapped[int] = mapped_column(Integer, default=0)
    ok: Mapped[bool] = mapped_column(Boolean)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class _GscMetrics:
    """GSC の指標。掲載順位は「順位×表示回数」も持ち、集計では表示回数の重みつき平均にする（database_design.md §6）。"""

    clicks: Mapped[int] = mapped_column(Integer)
    impressions: Mapped[int] = mapped_column(Integer)
    position: Mapped[float] = mapped_column(Float)
    position_weighted: Mapped[float] = mapped_column(Float)


class GscSite(_GscMetrics, Base):
    """サイト全体（日付×国×デバイス）。サイト全体の数字はここから出す（database_design.md §4）。"""

    __tablename__ = "gsc_site"

    site_id: Mapped[int] = _site_fk()
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    country: Mapped[str] = mapped_column(String(16), primary_key=True)
    device: Mapped[str] = mapped_column(String(16), primary_key=True)


class GscPage(_GscMetrics, Base):
    """ページ（日付×ページ×デバイス）。ページはパスにそろえる（database_design.md §7）。"""

    __tablename__ = "gsc_page"

    site_id: Mapped[int] = _site_fk()
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    page: Mapped[str] = mapped_column(Text, primary_key=True)
    device: Mapped[str] = mapped_column(String(16), primary_key=True)


class GscQueryPage(_GscMetrics, Base):
    """クエリ×ページ（日付）。伏せられたクエリと、月ごとに整理した少ないクエリは入らない（data_sources.md §3）。"""

    __tablename__ = "gsc_query_page"

    site_id: Mapped[int] = _site_fk()
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    query: Mapped[str] = mapped_column(Text, primary_key=True)
    page: Mapped[str] = mapped_column(Text, primary_key=True)


class BingSiteDaily(Base):
    """Bing のサイト全体の日次（GetRankAndTrafficStats）。raw は API が返した1件そのもの（後から取り直せないため）。"""

    __tablename__ = "bing_site_daily"

    site_id: Mapped[int] = _site_fk()
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    clicks: Mapped[int] = mapped_column(Integer)
    impressions: Mapped[int] = mapped_column(Integer)
    raw: Mapped[dict] = mapped_column(JSONB)


class BingPageWeekly(Base):
    """Bing のページ別の週次（GetPageStats。上位100ページのみ）。week は API が返す週の日付。"""

    __tablename__ = "bing_page_weekly"

    site_id: Mapped[int] = _site_fk()
    week: Mapped[date] = mapped_column(Date, primary_key=True)
    page: Mapped[str] = mapped_column(Text, primary_key=True)
    clicks: Mapped[int] = mapped_column(Integer)
    impressions: Mapped[int] = mapped_column(Integer)
    position: Mapped[float | None] = mapped_column(Float)  # 表示されたときの平均掲載順位
    raw: Mapped[dict] = mapped_column(JSONB)


class BingCrawlDaily(Base):
    """Bing のクロールの日次（GetCrawlStats）。インデックス数・被リンク数はその日の在庫なので足さない。"""

    __tablename__ = "bing_crawl_daily"

    site_id: Mapped[int] = _site_fk()
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    crawled: Mapped[int] = mapped_column(Integer)
    indexed: Mapped[int] = mapped_column(Integer)
    backlinks: Mapped[int] = mapped_column(Integer)
    crawl_errors: Mapped[int] = mapped_column(Integer)
    raw: Mapped[dict] = mapped_column(JSONB)


class SitemapUrl(Base):
    """サイトマップに載っている URL（パスにそろえる）。取り込みのたびに入れ替える（前回読めなかったら前のまま）。

    検索に出たページ（gsc_page で imp 1回以上）と突き合わせて、インデックスの目安を出す（screen_design.md §7）。
    """

    __tablename__ = "sitemap_urls"

    site_id: Mapped[int] = _site_fk()
    path: Mapped[str] = mapped_column(Text, primary_key=True)
