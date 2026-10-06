"""SQLAlchemy engine/session plumbing."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.database_url,
    echo=settings.db_echo,
    pool_pre_ping=True,
    connect_args=connect_args,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables. Small project, so we skip Alembic on purpose."""
    from app import models  # noqa: F401  (import registers the mappers)

    Base.metadata.create_all(bind=engine)
