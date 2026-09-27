from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress

from app.agents.workflows import WorkflowRunner
from app.repositories.repository import Repository
from app.services.exporter import ArtifactExporter


LOGGER = logging.getLogger(__name__)


class TaskManager:
    def __init__(
        self, repository: Repository, workflows: WorkflowRunner, exporter: ArtifactExporter
    ) -> None:
        self.repository = repository
        self.workflows = workflows
        self.exporter = exporter
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.worker: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self.repository.mark_stale_tasks_failed()
        self.worker = asyncio.create_task(self._worker(), name="agent-task-worker")

    async def stop(self) -> None:
        if self.worker:
            self.worker.cancel()
            with suppress(asyncio.CancelledError):
                await self.worker

    async def submit(self, task_id: str) -> None:
        await self.queue.put(task_id)

    async def _worker(self) -> None:
        while True:
            task_id = await self.queue.get()
            try:
                await asyncio.to_thread(self._execute, task_id)
            finally:
                self.queue.task_done()

    def _execute(self, task_id: str) -> None:
        task = self.repository.get_task(task_id)
        if not task:
            return
        self.repository.update_task(task_id, status="running")
        try:
            result = self.workflows.run(task_id, task.task_type, json.loads(task.input_json))
            status = result.get("status", "completed")
            title = {
                "market_research": "市场调研产品对比报告",
                "tender_generation": "招标文件草案",
                "compliance_review": "招标文件合规检测报告",
            }[task.task_type]
            paths = self.exporter.export(task_id, title, result)
            mime_types = {
                "json": "application/json",
                "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "pdf": "application/pdf",
            }
            for kind, path in paths.items():
                self.repository.add_artifact(task_id, kind, mime_types[kind], path)
            review_items = result.get("review_items", [])
            if review_items:
                self.repository.add_review_items(task_id, review_items)
            self.repository.update_task(task_id, status=status, output=result)
        except Exception as exc:
            LOGGER.exception("Agent task %s failed", task_id)
            self.repository.update_task(task_id, status="failed", error=str(exc))
