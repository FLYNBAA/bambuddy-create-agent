"""Synchronous PostgreSQL filament inventory primitives.

This module intentionally has no dependency on the service layer.  Psycopg is
imported lazily so row models and tests remain usable without a live database.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable


class InventoryConfigurationError(RuntimeError):
    """Raised when a database operation is requested without a database URL."""


class InventoryDataError(ValueError):
    """Raised when inventory data cannot satisfy a calibration request."""


@dataclass(frozen=True, slots=True)
class FilamentColorRecord:
    id: int
    name: str
    material: str
    brand: str
    hex_srgb: str | None
    source_type: str = "bambu_studio_display_srgb"
    hex_rgba: str | None = None
    red: int | None = None
    green: int | None = None
    blue: int | None = None
    alpha: int | None = None
    aliases: tuple[str, ...] = ()
    notes: str | None = None
    source_url: str | None = None
    source_retrieved_on: date | None = None


@dataclass(frozen=True, slots=True)
class FilamentColorMapping:
    """A deterministic source-name to inventory-color mapping."""

    source_name: str
    color_id: int
    target_name: str
    hex_srgb: str


# Useful as a stable contract for callers that need a row-shaped value.
InventoryColor = FilamentColorRecord


_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA_SQL = _ROOT / "migrations" / "001_filament_inventory.sql"
_SEED_SQL = _ROOT / "migrations" / "001_filament_inventory_seed.sql"


class FilamentInventoryRepository:
    """Small synchronous repository using psycopg 3 and parameterized filters.

    ``connection_factory`` is injectable for unit tests and must accept a DB
    URL, returning a psycopg connection. Credentials are never included in
    exceptions or logs by this class.
    """

    def __init__(self, db_url: str | None = None, *, connection_factory: Callable[[str], Any] | None = None) -> None:
        self._db_url = db_url
        self._connection_factory = connection_factory

    def _connect(self) -> Any:
        if not self._db_url:
            raise InventoryConfigurationError("A PostgreSQL database URL is required for inventory operations")
        if self._connection_factory is not None:
            return self._connection_factory(self._db_url)
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise InventoryConfigurationError("psycopg 3 is required for PostgreSQL inventory operations") from exc
        return psycopg.connect(self._db_url)

    def initialize_schema(self) -> None:
        """Apply the idempotent inventory foundation DDL."""
        self._execute_script(_SCHEMA_SQL.read_text(encoding="utf-8"))

    def seed_official_colors(self) -> None:
        """Insert the source-backed Bambu PLA Basic catalogue rows."""
        self._execute_script(_SEED_SQL.read_text(encoding="utf-8"))

    def _execute_script(self, sql: str) -> None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql)
            connection.commit()
        finally:
            connection.close()

    def list_active_colors(self, *, brand: str | None = None, material: str | None = None) -> list[FilamentColorRecord]:
        """List active colors, optionally restricted by exact brand/material."""
        filters = ["c.is_active"]
        params: list[str] = []
        if brand is not None:
            filters.append("b.name = %s")
            params.append(brand)
        if material is not None:
            filters.append("m.name = %s")
            params.append(material)
        sql = f"""
            SELECT c.id, c.name, m.name, b.name, c.hex_srgb, c.source_type,
                   c.hex_rgba, c.red, c.green, c.blue, c.alpha, c.notes,
                   c.source_url, c.source_retrieved_on,
                   COALESCE(array_agg(a.alias ORDER BY a.alias)
                            FILTER (WHERE a.alias IS NOT NULL), '{{}}') AS aliases
            FROM filament_colors AS c
            JOIN filament_brands AS b ON b.id = c.brand_id
            JOIN filament_material_types AS m ON m.id = c.material_type_id
            LEFT JOIN filament_color_aliases AS a ON a.filament_color_id = c.id
            WHERE {" AND ".join(filters)}
            GROUP BY c.id, c.name, m.name, b.name, c.hex_srgb, c.source_type,
                     c.hex_rgba, c.red, c.green, c.blue, c.alpha, c.notes,
                     c.source_url, c.source_retrieved_on
            ORDER BY b.name, m.name, c.name
        """
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchall()
        finally:
            connection.close()
        return [self._row_to_record(row) for row in rows]

    def colors_for_numeric_matching(self, *, brand: str | None = None, material: str | None = None) -> list[FilamentColorRecord]:
        """Return colors suitable for numeric calibration, rejecting unknown hex."""
        records = self.list_active_colors(brand=brand, material=material)
        missing = [record.name for record in records if not record.hex_srgb]
        if missing:
            scope = ", ".join(missing)
            raise InventoryDataError(
                "Numeric color matching requires authoritative sRGB hex values; "
                f"missing values for: {scope}"
            )
        return records

    @staticmethod
    def _row_to_record(row: Iterable[Any]) -> FilamentColorRecord:
        values = tuple(row)
        aliases = values[14] or ()
        return FilamentColorRecord(
            id=int(values[0]), name=values[1], material=values[2], brand=values[3],
            hex_srgb=values[4], source_type=values[5], hex_rgba=values[6],
            red=values[7], green=values[8], blue=values[9], alpha=values[10],
            notes=values[11], source_url=values[12], source_retrieved_on=values[13],
            aliases=tuple(aliases),
        )
