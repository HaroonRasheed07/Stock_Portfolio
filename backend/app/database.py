"""
Stock Portfolio Intelligence Platform - Database Setup
SQLAlchemy async-ready engine with SQLite (PostgreSQL-compatible structure).
"""
import logging
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Session
from app.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


def _get_engine():
    """Create database engine based on configuration."""
    settings = get_settings()
    db_url = settings.DATABASE_URL

    # For SQLite, resolve relative paths against DATA_DIR
    if db_url.startswith("sqlite"):
        # Extract the filename from the URL (handles both relative and absolute paths)
        import re as _re
        match = _re.match(r'sqlite:///+(.*)', db_url)
        if match:
            path_part = match.group(1)
            # If the path is relative (starts with ./ or no drive letter), resolve against DATA_DIR
            if path_part.startswith("./") or (not _re.match(r'[A-Za-z]:', path_part) and not path_part.startswith("/")):
                # Strip any leading ./ and directory prefixes that duplicate DATA_DIR
                filename = path_part.lstrip("./")
                # If filename contains a directory prefix like "data/portfolio.db", extract just the filename
                if "/" in filename:
                    filename = filename.split("/")[-1]
                elif "\\" in filename:
                    filename = filename.split("\\")[-1]
                abs_path = str(settings.DATA_DIR / filename)
                db_url = f"sqlite:///{abs_path}"
                logger.info(f"Resolved SQLite path: {db_url}")

    # For SQLite, ensure the directory exists
    if db_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
        engine = create_engine(
            db_url,
            connect_args=connect_args,
            echo=False,
            pool_pre_ping=True,
        )
        # Enable WAL mode for better concurrent read performance
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA cache_size=-64000")  # 64MB cache
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    else:
        # PostgreSQL or other databases
        engine = create_engine(
            db_url,
            echo=False,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
        )

    return engine


# Engine and session factory
engine = _get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    """Dependency that provides a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables."""
    # Import all models so they are registered with Base
    from app.models import (  # noqa: F401
        portfolio,
        holding,
        snapshot,
        watchlist,
        alert,
        stock_cache,
        settings,
        catalyst,
    )
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialized successfully.")


def reset_db():
    """Drop and recreate all tables (development only)."""
    from app.models import (  # noqa: F401
        portfolio,
        holding,
        snapshot,
        watchlist,
        alert,
        stock_cache,
        settings,
        catalyst,
    )
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    logger.info("Database reset complete.")
