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

    if "reputation_score" not in columns:
        statements.append("ALTER TABLE telegram_users ADD COLUMN reputation_score INTEGER NOT NULL DEFAULT 0")

    if "reputation_dispute_losses" not in columns:
        statements.append(
            "ALTER TABLE telegram_users ADD COLUMN reputation_dispute_losses INTEGER NOT NULL DEFAULT 0"
        )

    if "reputation_updated_at" not in columns:
        statements.append(
            "ALTER TABLE telegram_users ADD COLUMN reputation_updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
        )

    if "nickname" not in columns:
        statements.append("ALTER TABLE telegram_users ADD COLUMN nickname VARCHAR(255)")

    if "nickname_changed_at" not in columns:
        statements.append("ALTER TABLE telegram_users ADD COLUMN nickname_changed_at DATETIME")

    for statement in statements:
        connection.execute(text(statement))

    if not inspector.has_table("user_reviews"):
        connection.execute(text(
            """
            CREATE TABLE user_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rater_telegram_id BIGINT NOT NULL,
                rated_telegram_id BIGINT NOT NULL,
                deal_id INTEGER,
                score INTEGER NOT NULL,
                comment TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        ))
        connection.execute(text("CREATE INDEX ix_user_reviews_rater_telegram_id ON user_reviews (rater_telegram_id)"))
        connection.execute(text("CREATE INDEX ix_user_reviews_rated_telegram_id ON user_reviews (rated_telegram_id)"))
        connection.execute(text("CREATE INDEX ix_user_reviews_deal_id ON user_reviews (deal_id)"))