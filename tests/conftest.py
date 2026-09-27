from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture()
def client(tmp_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        upload_dir=tmp_path / "uploads",
        artifact_dir=tmp_path / "artifacts",
        llm_mode="mock",
        web_search_enabled=False,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def wait_for_task(client: TestClient, task_id: str, timeout: float = 8.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/tasks/{task_id}")
        assert response.status_code == 200
        task = response.json()
        if task["status"] not in {"pending", "running"}:
            return task
        time.sleep(0.05)
    raise AssertionError(f"task {task_id} did not finish")
