from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from cerber_bot.config import resolve_database_url, sqlite_storage_path
from cerber_bot.db.base import Base


def ensure_database_parent(database_url: str) -> None:
    sqlite_path = sqlite_storage_path(database_url)
    if sqlite_path is not None:
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)


def create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(resolve_database_url(database_url), future=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_database(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(apply_lightweight_migrations)


def apply_lightweight_migrations(connection) -> None:  # type: ignore[no-untyped-def]
    if connection.dialect.name != "sqlite":
        return

    inspector = inspect(connection)
    if not inspector.has_table("telegram_users"):
        return

    columns = {column["name"] for column in inspector.get_columns("telegram_users")}
    statements: list[str] = []

    if "balance" not in columns:
        statements.append("ALTER TABLE telegram_users ADD COLUMN balance NUMERIC NOT NULL DEFAULT 0")

    if "held_balance" not in columns:
        statements.append("ALTER TABLE telegram_users ADD COLUMN held_balance NUMERIC NOT NULL DEFAULT 0")

    if "balance_currency" not in columns:
        statements.append("ALTER TABLE telegram_users ADD COLUMN balance_currency VARCHAR(8) NOT NULL DEFAULT 'USD'")

    if "display_name" not in columns:
        statements.append("ALTER TABLE telegram_users ADD COLUMN display_name VARCHAR(64)")

    if "name_changed_at" not in columns:
        statements.append("ALTER TABLE telegram_users ADD COLUMN name_changed_at DATETIME")

    if "referrer_telegram_id" not in columns:
        statements.append("ALTER TABLE telegram_users ADD COLUMN referrer_telegram_id BIGINT")

    if inspector.has_table("escrow_deals"):
        deal_columns = {column["name"] for column in inspector.get_columns("escrow_deals")}
        if "dispute_topic_id" not in deal_columns:
            statements.append("ALTER TABLE escrow_deals ADD COLUMN dispute_topic_id INTEGER")
        if "pending_actor" not in deal_columns:
            statements.append("ALTER TABLE escrow_deals ADD COLUMN pending_actor VARCHAR(8)")
        if "funds_held" not in deal_columns:
            statements.append("ALTER TABLE escrow_deals ADD COLUMN funds_held BOOLEAN NOT NULL DEFAULT 1")
        if "delivered_at" not in deal_columns:
            statements.append("ALTER TABLE escrow_deals ADD COLUMN delivered_at DATETIME")

    for statement in statements:
        connection.execute(text(statement))