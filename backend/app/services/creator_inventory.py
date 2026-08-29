"""Adapt Bambuddy's active spool inventory to creator color calibration."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from backend.app.core.database import async_session
from backend.app.models.spool import Spool


@dataclass(frozen=True, slots=True)
class CreatorInventoryColor:
    id: str
    name: str
    material: str
    brand: str
    hex_srgb: str
    aliases: tuple[str, ...] = ()


def _hex_srgb(rgba: str | None) -> str | None:
    value = (rgba or "").strip().removeprefix("#")
    if len(value) not in {6, 8} or any(char not in "0123456789abcdefABCDEF" for char in value):
        return None
    return f"#{value[:6].upper()}"


async def active_creator_inventory_colors() -> list[CreatorInventoryColor]:
    """Return every active Bambuddy spool with an authoritative display color."""
    async with async_session() as db:
        result = await db.execute(select(Spool).where(Spool.archived_at.is_(None)).order_by(Spool.id))
        spools = result.scalars().all()
    colors: list[CreatorInventoryColor] = []
    for spool in spools:
        hex_srgb = _hex_srgb(spool.rgba)
        if not hex_srgb:
            continue
        material = (spool.material or "").strip()
        if not material:
            continue
        colors.append(
            CreatorInventoryColor(
                id=str(spool.id),
                name=(spool.color_name or f"{spool.brand or 'Bambuddy'} {material}").strip(),
                material=material,
                brand=(spool.brand or "Bambuddy").strip(),
                hex_srgb=hex_srgb,
                aliases=tuple(filter(None, (spool.color_name, spool.slicer_filament_name))),
            )
        )
    return colors
