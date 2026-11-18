from collections.abc import Generator
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_engines: dict[Path, Engine] = {}
_session_factories: dict[Path, sessionmaker[Session]] = {}


def get_engine(db_path: Path | None = None) -> Engine:
    resolved_path = (db_path or get_settings().db_path).resolve()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    engine = _engines.get(resolved_path)
    if engine is None:
        sqlite_url = f"sqlite:///{resolved_path.as_posix()}"
        engine = create_engine(
            sqlite_url,
            connect_args={"check_same_thread": False},
            future=True,
        )

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        _engines[resolved_path] = engine
        _session_factories[resolved_path] = sessionmaker(
            bind=engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
    return engine


def init_db(db_path: Path | None = None) -> None:
    import app.models  # noqa: F401

    engine = get_engine(db_path)
    Base.metadata.create_all(bind=engine)


def get_session_factory(db_path: Path | None = None) -> sessionmaker[Session]:
    resolved_path = (db_path or get_settings().db_path).resolve()
    if resolved_path not in _session_factories:
        init_db(resolved_path)
    return _session_factories[resolved_path]


def get_db() -> Generator[Session, None, None]:
    settings = get_settings()
    init_db(settings.db_path)
    factory = get_session_factory(settings.db_path)
    session = factory()
    try:
        yield session
    finally:
        session.close()
