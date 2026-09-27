from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models import entities  # noqa: F401


class Database:
    def __init__(self, url: str) -> None:
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self.engine = create_engine(url, connect_args=connect_args, future=True)
        self.session_factory = sessionmaker(
            bind=self.engine, class_=Session, expire_on_commit=False, future=True
        )

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)
        if self.engine.dialect.name == "sqlite":
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "CREATE VIRTUAL TABLE IF NOT EXISTS source_chunks_fts "
                        "USING fts5(content, section, document_id UNINDEXED)"
                    )
                )

    def dispose(self) -> None:
        self.engine.dispose()

