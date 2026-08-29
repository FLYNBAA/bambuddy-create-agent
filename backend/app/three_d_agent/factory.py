"""Composition root for the production 3D printing agent."""

from __future__ import annotations

from .config import Settings, get_settings
from .service import ThreeDPrintAgent


def create_agent(
    settings: Settings | None = None,
    *,
    inventory_colors=None,
) -> ThreeDPrintAgent:
    from .providers import (
        DeepSeekBriefEnricher,
        DeepSeekColorMatcher,
        MeshyPrintProvider,
        OpenAICompatibleImageGenerator,
        TencentHunyuan3DGenerator,
    )
    from .filament_inventory import FilamentInventoryRepository
    from .storage import ArtifactStore, SessionRepository

    resolved_settings = settings if settings is not None else get_settings()
    inventory_url = resolved_settings.filament_database_url.get_secret_value().strip()
    return ThreeDPrintAgent(
        repository=SessionRepository(resolved_settings),
        artifact_store=ArtifactStore(resolved_settings),
        brief_enricher=DeepSeekBriefEnricher(resolved_settings),
        image_generator=OpenAICompatibleImageGenerator(resolved_settings),
        three_d_generator=TencentHunyuan3DGenerator(resolved_settings),
        print_provider=MeshyPrintProvider(resolved_settings),
        color_matcher=DeepSeekColorMatcher(resolved_settings),
        filament_inventory=FilamentInventoryRepository(inventory_url) if inventory_url else None,
        inventory_colors=inventory_colors,
    )
