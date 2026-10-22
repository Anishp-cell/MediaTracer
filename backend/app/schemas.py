from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Family = Literal["image", "document", "video", "audio", "spreadsheet"]


class ModelStatus(BaseModel):
    model_id: str
    state: str
    error: str | None
    device: str | None
    dtype: str | None
    gpu: str | None
    modalities: list[str]
    modality_errors: dict[str, str] = {}
    input_forms: dict[str, str] = {}
    load_seconds: float | None
    embedding_dim: int


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    model: ModelStatus
    indexed_files: int
    indexed_items: int


class AdapterCapability(BaseModel):
    family: str
    formats: dict[str, str]
    enabled: bool
    reason: str | None = None


class Capabilities(BaseModel):
    adapters: list[AdapterCapability]
    accepted_extensions: list[str]
    max_upload_mb: int
    image_query: bool
    video_refine: bool


class Registration(BaseModel):
    file_id: str | None
    filename: str
    action: Literal["new", "updated", "unchanged", "duplicate", "rejected"]
    reason: str | None = None


class IndexResponse(BaseModel):
    job_id: str | None
    files: list[Registration]


class LocalIndexRequest(BaseModel):
    paths: list[str] = Field(min_length=1, max_length=100)
    recursive: bool = True


class Job(BaseModel):
    id: str
    status: str
    file_ids: list[str]
    total: int
    done: int
    failed: int
    current: str | None
    progress: float
    message: str | None
    errors: list[dict[str, Any]]
    created_at: float
    updated_at: float


class FileInfo(BaseModel):
    id: str
    filename: str
    family: str
    format: str
    origin: Literal["upload", "local"]
    size_bytes: int
    sha256: str
    status: str
    error: str | None
    item_count: int
    created_at: float
    indexed_at: float | None
    modified_at: float | None
    model_id: str | None
    source_path: str | None = None  # only for local files (the user's own path)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    families: list[Family] | None = None
    limit: int = Field(default=20, ge=1, le=100)
    mode: Literal["semantic", "hybrid"] = "semantic"
    max_per_file: int = Field(default=3, ge=1, le=50)


class SearchResult(BaseModel):
    rank: int
    item_id: str
    file_id: str
    filename: str
    family: str
    kind: str
    modality: str
    match_type: str
    locator: dict[str, Any]
    location_label: str
    text: str | None
    preview_url: str | None
    original_url: str
    open_url: str
    score: float
    semantic_score: float
    keyword_score: float
    relative: float
    strength: Literal["strong", "moderate", "weak"]
    also_matched: list[str]


class SearchResponse(BaseModel):
    query: str
    mode: str
    families: list[str] | None
    results: list[SearchResult]
    searched_items: int
    took_ms: float
    notice: str | None = None


class RefineRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    step: float = Field(default=0.5, ge=0.1, le=5)


class RefineResponse(BaseModel):
    item_id: str
    coarse_time: float
    best_time: float
    best_score: float
    samples: list[dict[str, float]]
