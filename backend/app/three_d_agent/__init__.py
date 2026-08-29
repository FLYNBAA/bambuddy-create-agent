"""Composable 3D printing agent backend."""

from .contracts import (
    ColorMatchAssignment,
    ColorMatchResponse,
    CreativeBrief,
    ConversationMessage,
    ModelRepairState,
    PrintAnalysisState,
    PrintFileState,
    PrintabilityMetrics,
    PrintabilityReport,
    SessionSnapshot,
    SessionStatus,
    SubworkflowStatus,
)
from .calibration import (
    CalibrationError,
    CalibrationInspection,
    CalibrationLimits,
    CalibrationReport,
    CalibrationResult,
    ColorAssignment,
    ColorMapping,
    InventoryColor,
    SourceColor,
    calibrate_3mf,
    inspect_3mf,
    geometry_only_3mf,
)
from .filament_inventory import (
    FilamentColorMapping,
    FilamentColorRecord,
    FilamentInventoryRepository,
    InventoryConfigurationError,
    InventoryDataError,
)

from .factory import create_agent
from .service import ThreeDPrintAgent

__all__ = [
    "CreativeBrief",
    "ModelRepairState",
    "ConversationMessage",
    "PrintAnalysisState",
    "PrintFileState",
    "PrintabilityMetrics",
    "PrintabilityReport",
    "SubworkflowStatus",
    "SessionSnapshot",
    "SessionStatus",
    "ThreeDPrintAgent",
    "create_agent",
    "CalibrationError",
    "CalibrationInspection",
    "CalibrationLimits",
    "CalibrationReport",
    "CalibrationResult",
    "ColorAssignment",
    "ColorMapping",
    "InventoryColor",
    "SourceColor",
    "ColorMatchAssignment",
    "ColorMatchResponse",
    "calibrate_3mf",
    "inspect_3mf",
    "geometry_only_3mf",
    "FilamentColorMapping",
    "FilamentColorRecord",
    "FilamentInventoryRepository",
    "InventoryConfigurationError",
    "InventoryDataError",
]
