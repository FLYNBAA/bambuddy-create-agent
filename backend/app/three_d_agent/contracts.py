"""Public contracts for the composable 3D printing agent."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from enum import StrEnum
from math import isfinite
from pathlib import Path
from secrets import token_urlsafe
from typing import Literal, Protocol

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, computed_field, field_validator


class SessionStatus(StrEnum):
    NEEDS_INPUT = "needs_input"
    READY_FOR_IMAGES = "ready_for_images"
    QUEUED_IMAGE = "queued_image"
    GENERATING_IMAGES = "generating_images"
    AWAITING_IMAGE_SELECTION = "awaiting_image_selection"
    QUEUED_3D = "queued_3d"
    GENERATING_3D = "generating_3d"
    COMPLETED = "completed"
    FAILED = "failed"



class SubworkflowStatus(StrEnum):
    NOT_STARTED = "not_started"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class PrintabilityMetrics(BaseModel):
    is_watertight: bool
    volume: float = Field(ge=0)
    non_manifold_edges: int = Field(ge=0)
    degenerate_faces: int = Field(ge=0)
    holes: int = Field(ge=0)

    @field_validator("volume")
    @classmethod
    def volume_must_be_finite(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("volume must be finite")
        return value


class PrintabilityReport(BaseModel):
    status: str = Field(pattern="^(healthy|warning|error|unknown)$")
    metrics: PrintabilityMetrics


class PrintAnalysisState(BaseModel):
    status: SubworkflowStatus = SubworkflowStatus.NOT_STARTED
    report: PrintabilityReport | None = None
    score: int | None = Field(default=None, ge=0, le=100)
    insights: list[str] = Field(default_factory=list, max_length=8)
    error: str | None = None


class ModelRepairState(BaseModel):
    status: SubworkflowStatus = SubworkflowStatus.NOT_STARTED
    report: PrintabilityReport | None = None
    textures_preserved: bool = False
    error: str | None = None


class PrintFileState(BaseModel):
    """Internal Meshy conversion state; only calibration publishes an artifact."""

    status: SubworkflowStatus = SubworkflowStatus.NOT_STARTED
    max_colors: int | None = Field(default=None, ge=1, le=8)
    error: str | None = None

class ColorMatchAssignment(BaseModel):
    """One explicit DeepSeek decision for a source color."""

    source_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?$")
    inventory_id: str = Field(min_length=1, max_length=128)
    inventory_name: str | None = Field(default=None, max_length=120)
    matched_hex_srgb: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    rationale: str | None = Field(default=None, max_length=500)


class ColorCalibrationState(BaseModel):
    status: SubworkflowStatus = SubworkflowStatus.NOT_STARTED
    mode: Literal["white", "multicolor"] | None = None
    source_colors: list[str] = Field(default_factory=list)
    assignments: list[ColorMatchAssignment] = Field(default_factory=list)
    error: str | None = None



class CreativeBrief(BaseModel):
    """The three required decisions for creative generation."""

    subject: str | None = Field(default=None, max_length=500)
    style: str | None = Field(default=None, max_length=120)
    product_type: str | None = Field(default=None, max_length=120)
    details: str | None = Field(default=None, max_length=1000)

    @computed_field
    @property
    def missing_fields(self) -> list[str]:
        return [
            field
            for field in ("subject", "style", "product_type")
            if not getattr(self, field)
        ]

    @property
    def is_complete(self) -> bool:
        return not self.missing_fields


class BriefExtraction(BaseModel):
    """Structured DeepSeek result. Existing values may be repeated, never erased."""

    subject: str | None = None
    style: str | None = None
    product_type: str | None = None
    details: str | None = None


class ClarificationQuestion(BaseModel):
    field: str
    prompt: str
    options: list[str]


class StageEvent(BaseModel):
    stage: str
    status: str
    message: str
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))



class SessionSnapshot(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: str
    status: SessionStatus
    provider_capability_token: str = Field(default_factory=lambda: token_urlsafe(32), min_length=32, max_length=128)
    brief: CreativeBrief = Field(default_factory=CreativeBrief)
    questions: list[ClarificationQuestion] = Field(default_factory=list)
    image_prompt: str | None = None
    reference_image_path: str | None = None
    generated_image_paths: list[str] = Field(default_factory=list)
    selected_image_index: int | None = Field(default=None, ge=0, le=3)
    model_path: str | None = None
    model_preview_url: str | None = None
    provider_job_id: str | None = None
    repaired_model_path: str | None = None
    geometry_status: SubworkflowStatus = SubworkflowStatus.NOT_STARTED
    print_file_path: str | None = None
    print_analysis: PrintAnalysisState = Field(default_factory=PrintAnalysisState)
    model_repair: ModelRepairState = Field(default_factory=ModelRepairState)
    print_file: PrintFileState = Field(default_factory=PrintFileState)
    color_calibration: ColorCalibrationState = Field(default_factory=ColorCalibrationState)
    calibrated_print_file_path: str | None = None
    geometry_print_file_path: str | None = None

    error: str | None = None
    events: list[StageEvent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GeneratedImage(BaseModel):
    content: bytes
    media_type: str = "image/png"
    revised_prompt: str | None = None


class GeneratedModel(BaseModel):
    job_id: str
    glb_url: str
    preview_url: str | None = None




class ColorMatchResponse(BaseModel):
    assignments: list[ColorMatchAssignment] = Field(
        min_length=1,
        max_length=8,
        validation_alias=AliasChoices("assignments", "matches"),
    )


class PrintAssessment(BaseModel):
    """A concise quality assessment, intentionally without remediation advice."""

    score: int = Field(ge=0, le=100)
    insights: list[str] = Field(min_length=1, max_length=8)


class GeneratedTaskTitle(BaseModel):
    title: str = Field(min_length=1, max_length=120)


ProgressCallback = Callable[[str, str], Awaitable[None]]
ImageProgressCallback = Callable[[int, GeneratedImage], Awaitable[None]]


class BriefEnricher(Protocol):
    async def enrich(
        self,
        user_input: str,
        current: CreativeBrief,
        has_reference_image: bool,
    ) -> CreativeBrief: ...

class FilamentColorMatcher(Protocol):
    async def match_colors(
        self,
        source_colors: list[dict[str, object]],
        inventory: list[dict[str, object]],
    ) -> list[ColorMatchAssignment]: ...


class ImageGenerator(Protocol):
    async def generate(
        self,
        prompt: str,
        reference_image: Path | None = None,
        image_ready: ImageProgressCallback | None = None,
    ) -> list[GeneratedImage]: ...


class ThreeDGenerator(Protocol):
    async def generate(
        self,
        image_path: Path,
        progress: ProgressCallback | None = None,
    ) -> GeneratedModel: ...

class PrintProvider(Protocol):


    async def analyze(
        self,
        session_id: str,
        model_path: Path,
        public_route: str = "model",
        capability_token: str | None = None,
    ) -> PrintabilityReport: ...

    async def repair(self, session_id: str, model_path: Path) -> str: ...

    async def multi_color(
        self,
        session_id: str,
        model_path: Path,
        max_colors: int,
        capability_token: str | None = None,
    ) -> str: ...
