"""Tencent Hunyuan 3D Pro provider."""

from __future__ import annotations

import asyncio
import base64
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..config import Settings
from ..contracts import GeneratedModel, ProgressCallback
from .exceptions import ProviderConfigurationError, ProviderError

_API_VERSION = "2025-05-13"
_SERVICE = "ai3d"


class TencentHunyuan3DGenerator:
    """Submit and poll a Tencent Hunyuan 3D Pro image-to-GLB generation job."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Any | None = None

    async def generate(
        self,
        image_path: Path,
        progress: ProgressCallback | None = None,
    ) -> GeneratedModel:
        """Generate a GLB model from a local image and return only Tencent's GLB result."""
        self._validate_configuration()
        if not image_path.is_file():
            raise ProviderError("The generated image is unavailable for Hunyuan 3D generation.")

        try:
            image = await asyncio.to_thread(image_path.read_bytes)
        except OSError as exc:
            raise ProviderError("The generated image could not be read for Hunyuan 3D.") from exc
        if not image:
            raise ProviderError("The generated image is empty and cannot be sent to Hunyuan 3D.")

        await self._notify(progress, "generating_3d", "正在提交混元 3D 生成任务。")
        deadline = time.monotonic() + self._settings.hunyuan_timeout_seconds
        response = await self._call(
            "SubmitHunyuanTo3DProJob",
            {
                "ImageBase64": base64.b64encode(image).decode("ascii"),
                "GenerateType": "Normal",
                "FaceCount": self._settings.hunyuan_face_count,
                "EnablePBR": self._settings.hunyuan_enable_pbr,
            },
        )
        job_id = self._payload(response).get("JobId")
        if not isinstance(job_id, str) or not job_id:
            raise ProviderError("Hunyuan 3D submission did not return a job ID.")

        await self._notify(
            progress,
            "generating_3d",
            f"混元 3D 任务 {job_id} 已提交，正在等待 GLB 模型。",
        )
        return await self._poll(job_id, deadline, progress)

    async def _poll(
        self,
        job_id: str,
        deadline: float,
        progress: ProgressCallback | None,
    ) -> GeneratedModel:
        query_failures = 0
        poll_interval = self._settings.hunyuan_poll_interval_seconds
        failure_limit = self._settings.hunyuan_query_failure_limit

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProviderError("Hunyuan 3D generation timed out before returning a GLB model.")
            await asyncio.sleep(min(poll_interval, remaining))

            try:
                response = await self._call(
                    "QueryHunyuanTo3DProJob",
                    {"JobId": job_id},
                )
            except ProviderError as exc:
                query_failures += 1
                if query_failures >= failure_limit:
                    raise ProviderError(
                        "Hunyuan 3D status queries failed too many times."
                    ) from exc
                await self._notify(
                    progress,
                    "generating_3d",
                    "混元 3D 状态查询失败，正在重试。",
                )
                continue

            query_failures = 0
            payload = self._payload(response)
            status = payload.get("Status")
            normalized_status = status.upper() if isinstance(status, str) else ""

            if normalized_status == "DONE":
                model = self._completed_model(job_id, payload)
                await self._notify(
                    progress,
                    "generating_3d",
                    f"混元 3D 任务 {job_id} 已完成，GLB 模型已就绪。",
                )
                return model
            if normalized_status in {"FAIL", "FAILED"}:
                raise ProviderError("Hunyuan 3D generation job failed.")

            await self._notify(
                progress,
                "generating_3d",
                f"混元 3D 任务 {job_id} 当前状态：{normalized_status or '处理中'}。",
            )

    def _completed_model(self, job_id: str, payload: Mapping[str, Any]) -> GeneratedModel:
        results = payload.get("ResultFile3Ds")
        if not isinstance(results, list):
            raise ProviderError("Hunyuan 3D completed without a GLB model.")

        for result in results:
            if not isinstance(result, Mapping):
                continue
            result_type = result.get("Type")
            glb_url = result.get("Url")
            if (
                isinstance(result_type, str)
                and result_type.upper() == "GLB"
                and isinstance(glb_url, str)
                and glb_url
            ):
                preview_url = result.get("PreviewImageUrl")
                return GeneratedModel(
                    job_id=job_id,
                    glb_url=glb_url,
                    preview_url=preview_url if isinstance(preview_url, str) else None,
                )

        raise ProviderError("Hunyuan 3D completed without a GLB model.")

    async def _call(self, action: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            response = await asyncio.to_thread(self._call_sync, action, dict(params))
        except ProviderConfigurationError:
            raise
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"Hunyuan 3D {action} request failed.") from exc
        if not isinstance(response, Mapping):
            raise ProviderError(f"Hunyuan 3D {action} returned an invalid response.")
        return response

    def _call_sync(self, action: str, params: dict[str, Any]) -> Any:
        return self._client_for_call().call_json(action, params)

    def _client_for_call(self) -> Any:
        if self._client is not None:
            return self._client

        secret_id = self._settings.tencent_secret_id.get_secret_value().strip()
        secret_key = self._settings.tencent_secret_key.get_secret_value().strip()
        try:
            from tencentcloud.common.common_client import CommonClient
            from tencentcloud.common.credential import Credential
        except ImportError as exc:
            raise ProviderConfigurationError(
                "tencentcloud-sdk-python is required for Hunyuan 3D generation."
            ) from exc

        self._client = CommonClient(
            credential=Credential(secret_id, secret_key),
            region=self._settings.tencent_region,
            service=_SERVICE,
            version=_API_VERSION,
        )
        return self._client

    def _validate_configuration(self) -> None:
        if not self._settings.tencent_secret_id.get_secret_value().strip():
            raise ProviderConfigurationError(
                "Tencent SecretId is required for Hunyuan 3D generation."
            )
        if not self._settings.tencent_secret_key.get_secret_value().strip():
            raise ProviderConfigurationError(
                "Tencent SecretKey is required for Hunyuan 3D generation."
            )
        if not 3_000 <= self._settings.hunyuan_face_count <= 1_500_000:
            raise ProviderConfigurationError(
                "Hunyuan face count must be between 3000 and 1500000."
            )
        if self._settings.hunyuan_poll_interval_seconds <= 0:
            raise ProviderConfigurationError(
                "Hunyuan poll interval must be greater than zero."
            )
        if self._settings.hunyuan_timeout_seconds <= 0:
            raise ProviderConfigurationError(
                "Hunyuan timeout must be greater than zero."
            )
        if self._settings.hunyuan_query_failure_limit < 1:
            raise ProviderConfigurationError(
                "Hunyuan query failure limit must be at least one."
            )

    @staticmethod
    def _payload(response: Mapping[str, Any]) -> Mapping[str, Any]:
        payload = response.get("Response")
        return payload if isinstance(payload, Mapping) else response

    @staticmethod
    async def _notify(
        progress: ProgressCallback | None,
        stage: str,
        message: str,
    ) -> None:
        if progress is not None:
            await progress(stage, message)
