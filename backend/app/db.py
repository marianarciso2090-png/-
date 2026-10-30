from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()
engine_kwargs = {"pool_pre_ping": True}
if settings.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
engine = create_engine(settings.database_url, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_schema() -> None:
    # Importing here prevents circular model imports during app startup.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    # Preserve old reports, but do not expose records without a credential owner.
    with engine.begin() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("research_runs")}
        if "owner_id" not in columns:
            connection.execute(text("ALTER TABLE research_runs ADD COLUMN owner_id VARCHAR(64)"))
            connection.execute(text("CREATE INDEX ix_research_runs_owner_id ON research_runs (owner_id)"))
