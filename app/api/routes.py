from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse

from app.schemas.api import (
    ArtifactResponse,
    ComplianceReviewRequest,
    DocumentResponse,
    MarketResearchRequest,
    TaskResponse,
    TaskResultResponse,
    TenderGenerationRequest,
)


router = APIRouter(prefix="/api/v1")


def _task_response(task) -> TaskResponse:
    return TaskResponse(
        id=task.id,
        task_type=task.task_type,
        status=task.status,
        error=task.error,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


async def _create_task(request: Request, task_type: str, payload: dict) -> TaskResponse:
    task = request.app.state.repository.create_task(task_type, payload)
    await request.app.state.task_manager.submit(task.id)
    return _task_response(task)


@router.get("/health")
def health(request: Request) -> dict[str, str]:
    return {
        "status": "ok",
        "app": request.app.state.settings.app_name,
        "llm_mode": request.app.state.settings.llm_mode,
    }


@router.post("/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(request: Request, file: UploadFile = File(...)) -> DocumentResponse:
    try:
        document = await request.app.state.document_service.save_upload(file)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"文件解析失败: {exc}") from exc
    return DocumentResponse.model_validate(document, from_attributes=True)


@router.get("/documents/{document_id}", response_model=DocumentResponse)
def get_document(request: Request, document_id: str) -> DocumentResponse:
    document = request.app.state.repository.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")
    return DocumentResponse.model_validate(document, from_attributes=True)


@router.post("/tasks/market-research", response_model=TaskResponse, status_code=202)
async def create_market_task(request: Request, payload: MarketResearchRequest) -> TaskResponse:
    return await _create_task(request, "market_research", payload.model_dump(mode="json"))


@router.post("/tasks/tender-generation", response_model=TaskResponse, status_code=202)
async def create_tender_task(request: Request, payload: TenderGenerationRequest) -> TaskResponse:
    return await _create_task(request, "tender_generation", payload.model_dump(mode="json"))


@router.post("/tasks/compliance-review", response_model=TaskResponse, status_code=202)
async def create_compliance_task(request: Request, payload: ComplianceReviewRequest) -> TaskResponse:
    return await _create_task(request, "compliance_review", payload.model_dump(mode="json"))


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(request: Request, task_id: str) -> TaskResponse:
    task = request.app.state.repository.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _task_response(task)


@router.get("/tasks/{task_id}/result", response_model=TaskResultResponse)
def get_task_result(request: Request, task_id: str) -> TaskResultResponse:
    task = request.app.state.repository.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status in {"pending", "running"}:
        raise HTTPException(status_code=409, detail="任务尚未完成")
    if task.status == "failed":
        raise HTTPException(status_code=422, detail=task.error or "任务执行失败")
    artifacts = [
        ArtifactResponse(
            id=item.id,
            kind=item.kind,
            mime_type=item.mime_type,
            download_url=f"/api/v1/artifacts/{item.id}/download",
        )
        for item in request.app.state.repository.list_artifacts(task_id)
    ]
    return TaskResultResponse(
        task=_task_response(task), result=json.loads(task.output_json or "{}"), artifacts=artifacts
    )


@router.get("/artifacts/{artifact_id}/download")
def download_artifact(request: Request, artifact_id: str) -> FileResponse:
    artifact = request.app.state.repository.get_artifact(artifact_id)
    if not artifact or not Path(artifact.path).is_file():
        raise HTTPException(status_code=404, detail="产物不存在")
    return FileResponse(
        artifact.path,
        media_type=artifact.mime_type,
        filename=Path(artifact.path).name,
    )

