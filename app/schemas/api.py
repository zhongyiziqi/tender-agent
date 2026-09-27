from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class Indicator(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    operator: Literal[">=", "<=", "=", "contains"] = ">="
    target: str | float | int
    unit: str | None = None
    required: bool = True


class RequirementSpec(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    functions: list[str] = Field(default_factory=list)
    indicators: list[Indicator] = Field(default_factory=list)
    budget_min: float | None = Field(default=None, ge=0)
    budget_max: float | None = Field(default=None, ge=0)
    service_requirements: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_budget(self) -> "RequirementSpec":
        if (
            self.budget_min is not None
            and self.budget_max is not None
            and self.budget_min > self.budget_max
        ):
            raise ValueError("budget_min cannot exceed budget_max")
        return self


class ScoreWeights(BaseModel):
    price: float = Field(default=0.4, ge=0, le=1)
    performance: float = Field(default=0.4, ge=0, le=1)
    service: float = Field(default=0.2, ge=0, le=1)
    adjustment_reason: str | None = None

    @model_validator(mode="after")
    def validate_total(self) -> "ScoreWeights":
        if abs(self.price + self.performance + self.service - 1.0) > 1e-6:
            raise ValueError("price, performance and service weights must sum to 1")
        return self


class CandidateProduct(BaseModel):
    product_name: str = Field(min_length=1, max_length=200)
    vendor_name: str = Field(min_length=1, max_length=200)
    price: float | None = Field(default=None, gt=0)
    performance_score: float = Field(default=0, ge=0, le=100)
    service_score: float = Field(default=0, ge=0, le=100)
    meets_required: bool = True
    parameters: dict[str, Any] = Field(default_factory=dict)
    source_document_ids: list[str] = Field(default_factory=list)


class MarketResearchRequest(BaseModel):
    requirement: RequirementSpec
    document_ids: list[str] = Field(default_factory=list)
    weights: ScoreWeights = Field(default_factory=ScoreWeights)
    candidate_products: list[CandidateProduct] = Field(default_factory=list)


class TenderGenerationRequest(BaseModel):
    market_research_task_id: str


class ComplianceReviewRequest(BaseModel):
    generation_task_id: str | None = None
    document_id: str | None = None
    vendor_coverage_count: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_source(self) -> "ComplianceReviewRequest":
        if bool(self.generation_task_id) == bool(self.document_id):
            raise ValueError("provide exactly one of generation_task_id or document_id")
        return self


class DocumentResponse(BaseModel):
    id: str
    filename: str
    content_type: str
    size_bytes: int
    status: str
    created_at: datetime


class TaskResponse(BaseModel):
    id: str
    task_type: str
    status: str
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class ArtifactResponse(BaseModel):
    id: str
    kind: str
    mime_type: str
    download_url: str


class TaskResultResponse(BaseModel):
    task: TaskResponse
    result: dict[str, Any]
    artifacts: list[ArtifactResponse]

