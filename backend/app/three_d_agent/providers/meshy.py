"""Meshy print-analysis, repair, and multi-color task provider."""

from __future__ import annotations

import asyncio
import base64
import math
import struct
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

import httpx

from ..config import Settings
from ..contracts import PrintabilityMetrics, PrintabilityReport
from ..network import UnsafeRemoteURL, assert_public_http_url, httpx_route_kwargs, proxy_route_candidates
from .exceptions import ProviderConfigurationError, ProviderError

_MAX_GLB_INPUT_BYTES = 100 * 1024 * 1024
_TERMINAL_FAILURES = {"FAILED", "CANCELED", "CANCELLED"}
_PENDING_STATUSES = {"PENDING", "IN_PROGRESS", "QUEUED", "RUNNING"}


class MeshyPrintProvider:
    """Submit Meshy print tasks and poll them to their validated terminal result."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._trust_env: bool | None = None

    async def analyze(
        self,
        session_id: str,
        model_path: Path,
        public_route: Literal["model", "repaired-model"] = "model",
    ) -> PrintabilityReport:
        source = await self._model_source(session_id, model_path, public_route)
        task = await self._submit("analyze", {"model_url": source})
        completed = await self._poll("analyze", task)
        return self._printability(completed)

    async def repair(self, session_id: str, model_path: Path) -> str:
        source = await self._model_source(session_id, model_path)
        task = await self._submit("repair", {"model_url": source})
        completed = await self._poll("repair", task)
        return self._model_url(completed, "glb")

    async def multi_color(
        self,
        session_id: str,
        model_path: Path,
        max_colors: int,
    ) -> str:
        if not 1 <= max_colors <= 16:
            raise ProviderError("Meshy color count must be between 1 and 16.")
        source = await self._model_source(session_id, model_path)
        task = await self._submit(
            "multi-color",
            {"model_url": source, "max_colors": max_colors},
        )
        completed = await self._poll("multi-color", task)
        return self._model_url(completed, "3mf")

    async def _model_source(
        self,
        session_id: str,
        model_path: Path,
        public_route: Literal["model", "repaired-model"] = "model",
    ) -> str:
        self._validate_configuration()
        if self._settings.meshy_model_input_mode == "data_uri":
            return await asyncio.to_thread(self._data_uri, model_path)
        return self._public_model_url(session_id, public_route)

    def _data_uri(self, model_path: Path) -> str:
        try:
            if not model_path.is_file():
                raise ProviderError("The original GLB model is unavailable for Meshy.")
            input_size = model_path.stat().st_size
            if input_size > _MAX_GLB_INPUT_BYTES:
                raise ProviderError("The original GLB exceeds Meshy's 100 MB input limit.")
            content = model_path.read_bytes()
        except OSError as exc:
            raise ProviderError("The original GLB could not be read for Meshy.") from exc
        if not content:
            raise ProviderError("The original GLB is empty.")
        if len(content) < 12 or content[:4] != b"glTF":
            raise ProviderError("The original model is not a GLB file.")
        version, declared_size = struct.unpack("<II", content[4:12])
        if version != 2 or declared_size != len(content):
            raise ProviderError("The original GLB has an invalid header.")
        return "data:model/gltf-binary;base64," + base64.b64encode(content).decode("ascii")

    def _public_model_url(
        self,
        session_id: str,
        public_route: Literal["model", "repaired-model"],
    ) -> str:
        parsed = urlsplit(self._settings.app_public_base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ProviderConfigurationError(
                "APP_PUBLIC_BASE_URL must be an absolute HTTP(S) URL for Meshy public_url mode."
            )
        path = parsed.path.rstrip("/") + f"/api/v1/creator/sessions/{session_id}/{public_route}.glb"
        public_url = urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))
        try:
            assert_public_http_url(public_url)
        except UnsafeRemoteURL as exc:
            raise ProviderConfigurationError(
                "APP_PUBLIC_BASE_URL must resolve to a public address for Meshy public_url mode."
            ) from exc
        return public_url

    async def _submit(self, operation: str, payload: dict[str, Any]) -> str:
        response = await self._request(
            "POST",
            f"/openapi/v1/print/{operation}",
            safe_to_retry=operation == "analyze",
            json=payload,
        )
        result = response.get("result")
        if not isinstance(result, str) or not result:
            raise ProviderError("Meshy task submission returned an invalid response.")
        return result

    async def _poll(self, operation: str, task_id: str) -> Mapping[str, Any]:
        deadline = time.monotonic() + self._settings.meshy_timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProviderError("Meshy print task timed out.")
            await asyncio.sleep(min(self._settings.meshy_poll_interval_seconds, remaining))
            task = await self._request(
                "GET",
                f"/openapi/v1/print/{operation}/{task_id}",
                safe_to_retry=True,
            )
            status = task.get("status")
            if not isinstance(status, str):
                raise ProviderError("Meshy task returned an invalid status.")
            normalized = status.upper()
            if normalized == "SUCCEEDED":
                return task
            if normalized in _TERMINAL_FAILURES:
                raise ProviderError(self._task_error(task))
            if normalized not in _PENDING_STATUSES:
                raise ProviderError("Meshy task returned an unknown status.")

    async def _select_trust_env(self) -> bool:
        if self._trust_env is not None:
            return self._trust_env
        headers = {"Authorization": f"Bearer {self._settings.meshy_api_key.get_secret_value()}"}
        last_error: Exception | None = None
        base_url = self._api_base_url()
        routes = proxy_route_candidates(self._settings.meshy_proxy_mode)
        if self._settings.meshy_proxy_mode == "auto" and True in routes:
            routes = (True, False)
        for trust_env in routes:
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(20.0),
                    **httpx_route_kwargs(trust_env),
                ) as probe_client:
                    await probe_client.get(
                        f"{base_url}/openapi/v1/print/analyze/network-probe",
                        headers=headers,
                    )
                self._trust_env = trust_env
                return trust_env
            except httpx.HTTPError as exc:
                last_error = exc
        raise ProviderError(
            "Meshy is unreachable through configured proxy and direct routes."
        ) from last_error

    async def _request(
        self,
        method: str,
        path: str,
        *,
        safe_to_retry: bool = False,
        **kwargs: Any,
    ) -> Mapping[str, Any]:
        base_url = self._api_base_url()
        attempts = 3 if safe_to_retry else 1
        last_transport_error: httpx.HTTPError | None = None
        for attempt in range(attempts):
            try:
                trust_env = await self._select_trust_env()
                async with httpx.AsyncClient(
                    timeout=self._settings.meshy_timeout_seconds,
                    **httpx_route_kwargs(trust_env),
                ) as client:
                    response = await client.request(
                        method,
                        f"{base_url}{path}",
                        headers={"Authorization": f"Bearer {self._settings.meshy_api_key.get_secret_value()}"},
                        **kwargs,
                    )
                    response.raise_for_status()
                    payload = response.json()
                if not isinstance(payload, Mapping):
                    raise ProviderError("Meshy print request returned an invalid response.")
                return payload
            except httpx.HTTPStatusError as exc:
                raise ProviderError(
                    f"Meshy print request returned HTTP {exc.response.status_code}."
                ) from exc
            except httpx.HTTPError as exc:
                last_transport_error = exc
                self._trust_env = None
                if attempt + 1 < attempts:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
            except ValueError as exc:
                raise ProviderError("Meshy print request returned invalid JSON.") from exc
        raise ProviderError(
            "Meshy print request failed before receiving a response."
        ) from last_transport_error

    def _validate_configuration(self) -> None:
        self._api_base_url()
        if not self._settings.meshy_api_key.get_secret_value().strip():
            raise ProviderConfigurationError("MESHY_API_KEY is required for Meshy print tools.")
        if self._settings.meshy_model_input_mode not in {"data_uri", "public_url"}:
            raise ProviderConfigurationError("MESHY_MODEL_INPUT_MODE must be data_uri or public_url.")
        if self._settings.meshy_poll_interval_seconds <= 0:
            raise ProviderConfigurationError("Meshy poll interval must be greater than zero.")
        if self._settings.meshy_timeout_seconds <= 0:
            raise ProviderConfigurationError("Meshy timeout must be greater than zero.")

    def _api_base_url(self) -> str:
        try:
            parsed = urlsplit(self._settings.meshy_base_url)
            port = parsed.port
        except ValueError as exc:
            raise ProviderConfigurationError("MESHY_BASE_URL is invalid.") from exc
        if (
            parsed.scheme != "https"
            or parsed.hostname != "api.meshy.ai"
            or port not in {None, 443}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ProviderConfigurationError(
                "MESHY_BASE_URL must be exactly https://api.meshy.ai."
            )
        return "https://api.meshy.ai"

    @staticmethod
    def _task_error(task: Mapping[str, Any]) -> str:
        error = task.get("task_error")
        if isinstance(error, str) and error:
            return "Meshy print task failed."
        if isinstance(error, Mapping) and isinstance(error.get("message"), str):
            return "Meshy print task failed."
        return "Meshy print task failed."

    @staticmethod
    def _printability(task: Mapping[str, Any]) -> PrintabilityReport:
        payload = task.get("printability")
        if not isinstance(payload, Mapping):
            raise ProviderError("Meshy analysis completed without a printability report.")
        status = payload.get("status")
        metrics = payload.get("metrics")
        if status not in {"healthy", "warning", "error", "unknown"} or not isinstance(metrics, Mapping):
            raise ProviderError("Meshy analysis returned an invalid printability report.")
        required = {"is_watertight", "volume", "non_manifold_edges", "degenerate_faces", "holes"}
        if not required.issubset(metrics):
            raise ProviderError("Meshy analysis returned incomplete printability metrics.")
        volume = metrics["volume"]
        counts = ("non_manifold_edges", "degenerate_faces", "holes")
        if (
            not isinstance(metrics["is_watertight"], bool)
            or not isinstance(volume, (int, float))
            or isinstance(volume, bool)
            or not math.isfinite(float(volume))
            or volume < 0
            or any(
                not isinstance(metrics[name], int)
                or isinstance(metrics[name], bool)
                or metrics[name] < 0
                for name in counts
            )
        ):
            raise ProviderError("Meshy analysis returned invalid printability metrics.")
        return PrintabilityReport(
            status=status,
            metrics=PrintabilityMetrics(
                is_watertight=metrics["is_watertight"],
                volume=float(volume),
                non_manifold_edges=metrics["non_manifold_edges"],
                degenerate_faces=metrics["degenerate_faces"],
                holes=metrics["holes"],
            ),
        )

    @staticmethod
    def _model_url(task: Mapping[str, Any], extension: str) -> str:
        model_urls = task.get("model_urls")
        if not isinstance(model_urls, Mapping):
            raise ProviderError("Meshy task completed without a model URL.")
        url = model_urls.get(extension)
        if not isinstance(url, str) or not url:
            raise ProviderError("Meshy task completed without the requested model URL.")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ProviderError("Meshy task returned an invalid model URL.")
        return url
