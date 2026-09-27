from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agents.market_researcher import MarketResearcher
from app.agents.workflows import WorkflowRunner
from app.api.routes import router
from app.core.config import Settings, get_settings
from app.db.session import Database
from app.llm.factory import ModelFactory
from app.repositories.repository import Repository
from app.services.documents import DocumentService
from app.services.exporter import ArtifactExporter
from app.services.task_manager import TaskManager
from app.services.web_search import WebSearchService


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app_settings.prepare_directories()
        database = Database(app_settings.database_url)
        database.initialize()
        repository = Repository(database)
        model_factory = ModelFactory(app_settings)
        search_service = WebSearchService(app_settings)
        researcher = MarketResearcher(app_settings, model_factory, search_service)
        workflows = WorkflowRunner(repository, model_factory, researcher)
        task_manager = TaskManager(
            repository, workflows, ArtifactExporter(app_settings.artifact_dir)
        )
        app.state.settings = app_settings
        app.state.database = database
        app.state.repository = repository
        app.state.document_service = DocumentService(app_settings, repository)
        app.state.task_manager = task_manager
        await task_manager.start()
        try:
            yield
        finally:
            await task_manager.stop()
            database.dispose()

    logging.basicConfig(
        level=getattr(logging, app_settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    application = FastAPI(title=app_settings.app_name, version="0.1.0", lifespan=lifespan)
    application.include_router(router)
    return application


app = create_app()
