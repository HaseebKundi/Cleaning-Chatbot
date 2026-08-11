"""
SQLAlchemy engine/session. Reused as-is from the original project's pattern.
"""
import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import settings

logger = logging.getLogger("database")

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_lightweight_migrations() -> None:
    """Auto-add any model columns that don't exist yet on the live database.

    create_all() only creates tables that are missing entirely — it never
    alters an existing table, so adding a new column to a model (like `address`
    on Lead) silently does nothing to a database that already has that table.
    The app then crashes on the first INSERT that touches the new column.
    This is a lightweight stand-in for a real migration tool (Alembic) —
    fine for a small project like this, but worth graduating to Alembic if
    the schema keeps evolving after a client goes live with real data.
    """
    inspector = inspect(engine)
    for table in Base.metadata.tables.values():
        if not inspector.has_table(table.name):
            continue
        existing_cols = {col["name"] for col in inspector.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing_cols:
                continue
            col_type = col.type.compile(engine.dialect)
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {col.name} {col_type}"))
            logger.info(f"Migrated: added column '{col.name}' to '{table.name}'")
