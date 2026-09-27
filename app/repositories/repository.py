from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import select, text, update

from app.db.session import Database
from app.models import AgentRun, AgentTask, Artifact, Document, ReviewItem, SourceChunk


class Repository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_document(
        self,
        *,
        filename: str,
        content_type: str,
        path: Path,
        sha256: str,
        size_bytes: int,
        chunks: list[dict[str, Any]],
    ) -> Document:
        document = Document(
            id=str(uuid4()),
            filename=filename,
            content_type=content_type,
            path=str(path),
            sha256=sha256,
            size_bytes=size_bytes,
            status="parsed",
        )
        with self.database.session_factory.begin() as session:
            session.add(document)
            session.flush()
            for item in chunks:
                chunk = SourceChunk(document_id=document.id, **item)
                session.add(chunk)
                session.flush()
                if self.database.engine.dialect.name == "sqlite":
                    session.execute(
                        text(
                            "INSERT INTO source_chunks_fts(rowid, content, section, document_id) "
                            "VALUES (:id, :content, :section, :document_id)"
                        ),
                        {
                            "id": chunk.id,
                            "content": chunk.content,
                            "section": chunk.section or "",
                            "document_id": document.id,
                        },
                    )
        return document

    def get_document(self, document_id: str) -> Document | None:
        with self.database.session_factory() as session:
            return session.get(Document, document_id)

    def get_document_chunks(self, document_id: str) -> list[SourceChunk]:
        with self.database.session_factory() as session:
            return list(
                session.scalars(
                    select(SourceChunk)
                    .where(SourceChunk.document_id == document_id)
                    .order_by(SourceChunk.id)
                )
            )

    def search_chunks(
        self, query: str, document_ids: list[str] | None = None, limit: int = 12
    ) -> list[dict[str, Any]]:
        document_ids = document_ids or []
        with self.database.session_factory() as session:
            if query.strip() and self.database.engine.dialect.name == "sqlite":
                terms = [part.strip() for part in query.replace("，", " ").split() if part.strip()]
                fts_query = " OR ".join(f'"{term.replace(chr(34), "")}"' for term in terms[:12])
                if fts_query:
                    sql = (
                        "SELECT rowid, document_id, section, content FROM source_chunks_fts "
                        "WHERE source_chunks_fts MATCH :query"
                    )
                    params: dict[str, Any] = {"query": fts_query, "limit": limit}
                    if document_ids:
                        placeholders = ",".join(f":doc{i}" for i in range(len(document_ids)))
                        sql += f" AND document_id IN ({placeholders})"
                        params.update({f"doc{i}": value for i, value in enumerate(document_ids)})
                    sql += " ORDER BY rank LIMIT :limit"
                    try:
                        rows = session.execute(text(sql), params).mappings().all()
                        if rows:
                            return [dict(row) for row in rows]
                    except Exception:
                        pass

            statement = select(SourceChunk).order_by(SourceChunk.id).limit(limit)
            if document_ids:
                statement = statement.where(SourceChunk.document_id.in_(document_ids))
            chunks = session.scalars(statement).all()
            return [
                {
                    "rowid": item.id,
                    "document_id": item.document_id,
                    "section": item.section,
                    "content": item.content,
                    "page_number": item.page_number,
                }
                for item in chunks
            ]

    def create_task(self, task_type: str, input_data: dict[str, Any]) -> AgentTask:
        task = AgentTask(
            id=str(uuid4()),
            task_type=task_type,
            status="pending",
            input_json=json.dumps(input_data, ensure_ascii=False),
        )
        with self.database.session_factory.begin() as session:
            session.add(task)
        return task

    def get_task(self, task_id: str) -> AgentTask | None:
        with self.database.session_factory() as session:
            return session.get(AgentTask, task_id)

    def update_task(
        self,
        task_id: str,
        *,
        status: str,
        output: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        values: dict[str, Any] = {"status": status, "error": error}
        if output is not None:
            values["output_json"] = json.dumps(output, ensure_ascii=False)
        with self.database.session_factory.begin() as session:
            session.execute(update(AgentTask).where(AgentTask.id == task_id).values(**values))

    def mark_stale_tasks_failed(self) -> None:
        with self.database.session_factory.begin() as session:
            session.execute(
                update(AgentTask)
                .where(AgentTask.status == "running")
                .values(status="failed", error="服务重启，任务执行被中断，请重新提交")
            )

    def add_run(
        self, task_id: str, node_name: str, model_name: str, sources: list[dict[str, Any]]
    ) -> None:
        with self.database.session_factory.begin() as session:
            session.add(
                AgentRun(
                    id=str(uuid4()),
                    task_id=task_id,
                    node_name=node_name,
                    model_name=model_name,
                    sources_json=json.dumps(sources, ensure_ascii=False),
                )
            )

    def add_artifact(
        self, task_id: str, kind: str, mime_type: str, path: Path
    ) -> Artifact:
        artifact = Artifact(
            id=str(uuid4()),
            task_id=task_id,
            kind=kind,
            mime_type=mime_type,
            path=str(path),
        )
        with self.database.session_factory.begin() as session:
            session.add(artifact)
        return artifact

    def list_artifacts(self, task_id: str) -> list[Artifact]:
        with self.database.session_factory() as session:
            return list(
                session.scalars(select(Artifact).where(Artifact.task_id == task_id))
            )

    def get_artifact(self, artifact_id: str) -> Artifact | None:
        with self.database.session_factory() as session:
            return session.get(Artifact, artifact_id)

    def add_review_items(self, task_id: str, items: list[dict[str, str]]) -> None:
        with self.database.session_factory.begin() as session:
            for item in items:
                session.add(ReviewItem(id=str(uuid4()), task_id=task_id, **item))

