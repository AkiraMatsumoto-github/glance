"""Alembic の実行環境。接続先は sqlalchemy.url（テストで渡す）か、GLANCE_DATABASE_URL。"""

from alembic import context
from sqlalchemy import create_engine, pool

from glance.config import Settings
from glance.db.models import Base

config = context.config
target_metadata = Base.metadata


def database_url() -> str:
    return config.get_main_option("sqlalchemy.url") or Settings().database_url  # type: ignore[call-arg]


def run_migrations_offline() -> None:
    context.configure(url=database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # psycopg 3 は同期でも使えるので、マイグレーションは同期のエンジンで当てる
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
