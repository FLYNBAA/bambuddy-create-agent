"""DeepSeek-backed extraction of a structured creative brief."""

from __future__ import annotations

from typing import Any

import json
import httpx

from ..config import Settings
from ..contracts import (
    BriefExtraction,
    ColorMatchAssignment,
    ColorMatchResponse,
    CreativeBrief,
)
from ..network import httpx_route_kwargs, proxy_route_candidates
from .exceptions import ProviderConfigurationError, ProviderError

_FIELD_LIMITS = {
    "subject": 500,
    "style": 120,
    "product_type": 120,
    "details": 1000,
}


class DeepSeekBriefEnricher:
    """Extract only supplied creative-brief facts through DeepSeek's JSON mode."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._trust_env: bool | None = None

    async def enrich(
        self,
        user_input: str,
        current: CreativeBrief,
        has_reference_image: bool,
    ) -> CreativeBrief:
        """Return a brief augmented by valid, non-empty structured provider output."""
        try:
            preferred = await self._select_trust_env()
            routes = (preferred,) + tuple(
                route
                for route in proxy_route_candidates(self._settings.deepseek_proxy_mode)
                if route != preferred
            )
            last_error: Exception | None = None
            for index, trust_env in enumerate(routes):
                try:
                    async with httpx.AsyncClient(
                        timeout=self._settings.deepseek_timeout_seconds,
                        **httpx_route_kwargs(trust_env),
                    ) as client:
                        extracted = await self._model(client).ainvoke(
                            [
                                (
                                    "system",
                                    """Extract a 3D-print creative brief from the user's newest message.
Return JSON matching the requested schema. Extract subject, style, product_type,
and details. Put explicit color, pose, proportion, functional, structural, and
other production constraints in details without repeating the three required
fields. A value may be included only when the user states it or clearly corrects
an existing value. Use null for fields the newest message does not establish.
Never use an empty string to clear a field. Do not invent image contents: when a
reference image is present, it constrains the brief but is not visible to you.
Keep each value concise and omit commentary.""",
                                ),
                                (
                                    "human",
                                    (
                                        f"Current brief: {current.model_dump_json()}\n"
                                        f"Reference image supplied: {has_reference_image}\n"
                                        f"Newest user message: {user_input}"
                                    ),
                                ),
                            ]
                        )
                    self._trust_env = trust_env
                    break
                except Exception as exc:
                    last_error = exc
                    if index + 1 >= len(routes) or not self._is_transport_error(exc):
                        raise
            else:
                raise ProviderError("DeepSeek route selection failed.") from last_error
        except ProviderConfigurationError:
            raise
        except Exception as exc:
            raise ProviderError(
                f"DeepSeek brief enrichment failed ({type(exc).__name__})."
            ) from exc
        try:
            extraction = (
                extracted
                if isinstance(extracted, BriefExtraction)
                else BriefExtraction.model_validate(extracted)
            )
        except Exception as exc:
            raise ProviderError("DeepSeek returned an invalid creative brief.") from exc

        return CreativeBrief(
            **{
                field: self._valid_value(field, getattr(extraction, field))
                or getattr(current, field)
                for field in _FIELD_LIMITS
            }
        )

    async def _select_trust_env(self) -> bool:
        if self._trust_env is not None:
            return self._trust_env
        api_key = self._settings.deepseek_api_key.get_secret_value().strip()
        if not api_key:
            raise ProviderConfigurationError(
                "DeepSeek API key is required to enrich the creative brief."
            )
        last_error: Exception | None = None
        base_url = self._settings.deepseek_base_url.rstrip("/")
        for trust_env in proxy_route_candidates(self._settings.deepseek_proxy_mode):
            try:
                async with httpx.AsyncClient(
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=httpx.Timeout(10.0),
                    follow_redirects=True,
                    **httpx_route_kwargs(trust_env),
                ) as probe_client:
                    response = await probe_client.get(f"{base_url}/models")
                if response.status_code < 500:
                    self._trust_env = trust_env
                    return trust_env
            except httpx.HTTPError as exc:
                last_error = exc
        raise ProviderError(
            "DeepSeek is unreachable through direct and configured proxy routes."
        ) from last_error

    @staticmethod
    def _is_transport_error(error: Exception) -> bool:
        transport_errors = {
            "APIConnectionError",
            "APITimeoutError",
            "ConnectError",
            "ConnectTimeout",
            "ReadError",
            "ReadTimeout",
            "RemoteProtocolError",
            "WriteError",
            "WriteTimeout",
        }
        current: BaseException | None = error
        while current is not None:
            if type(current).__name__ in transport_errors:
                return True
            current = current.__cause__
    def _model(
        self,
        http_async_client: httpx.AsyncClient,
        schema: type[Any] = BriefExtraction,
        *,
        structured: bool = True,
    ) -> Any:
        api_key = self._settings.deepseek_api_key.get_secret_value().strip()
        if not api_key:
            raise ProviderConfigurationError(
                "DeepSeek API key is required for structured output."
            )

        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise ProviderConfigurationError(
                "langchain-openai is required for DeepSeek structured output."
            ) from exc

        model = ChatOpenAI(
            model=self._settings.deepseek_model,
            api_key=api_key,
            base_url=self._settings.deepseek_base_url.rstrip("/"),
            timeout=self._settings.deepseek_timeout_seconds,
            temperature=0,
            http_async_client=http_async_client,
            http_socket_options=(),
        )
        return model.with_structured_output(schema, method="json_mode") if structured else model

    @staticmethod
    def _valid_value(field: str, value: str | None) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        if not normalized:
            return None
        return normalized if len(normalized) <= _FIELD_LIMITS[field] else None


class DeepSeekColorMatcher(DeepSeekBriefEnricher):
    """Ask DeepSeek to assign each 3MF source color to an inventory ID."""

    async def match_colors(
        self,
        source_colors: list[dict[str, object]],
        inventory: list[dict[str, object]],
    ) -> list[ColorMatchAssignment]:
        if not source_colors or not inventory:
            raise ProviderError("DeepSeek color matching requires source colors and inventory.")
        messages = [
            (
                "system",
                """You are a filament color matching specialist. Return only JSON matching the schema.
For every source color, choose exactly one inventory_id from the supplied inventory.
Use the supplied sRGB display values and color names as evidence. Consider hue,
lightness, saturation, and semantic color names. Never invent an ID or color, never
merge source colors, and never omit a source color. Give a concise rationale.""",
            ),
            (
                "user",
                f"Source colors: {json.dumps(source_colors, ensure_ascii=False)}\n"
                f"Available inventory: {json.dumps(inventory, ensure_ascii=False)}",
            ),
        ]
        try:
            candidates = proxy_route_candidates(self._settings.deepseek_proxy_mode)
            routes = (
                (True,) + tuple(route for route in candidates if route is not True)
                if self._settings.deepseek_proxy_mode == "auto" and True in candidates
                else candidates
            )
            last_error: Exception | None = None
            response_payload: dict[str, object] | None = None
            for index, trust_env in enumerate(routes):
                try:
                    api_key = self._settings.deepseek_api_key.get_secret_value().strip()
                    async with httpx.AsyncClient(
                        timeout=max(180.0, self._settings.deepseek_timeout_seconds),
                        headers={"Authorization": f"Bearer {api_key}"},
                        **httpx_route_kwargs(trust_env),
                    ) as client:
                        response = await client.post(
                            f"{self._settings.deepseek_base_url.rstrip('/')}/chat/completions",
                            json={
                                "model": self._settings.deepseek_model,
                                "temperature": 0,
                                "max_tokens": 2000,
                                "thinking": {"type": "disabled"},
                                "response_format": {"type": "json_object"},
                                "messages": [
                                    {"role": role, "content": content}
                                    for role, content in messages
                                ],
                            },
                        )
                        response.raise_for_status()
                        response_payload = response.json()
                    self._trust_env = trust_env
                    break
                except httpx.HTTPStatusError as exc:
                    last_error = exc
                    raise ProviderError(
                        f"DeepSeek color matching request rejected (HTTP {exc.response.status_code})."
                    ) from exc
                except Exception as exc:
                    last_error = exc
                    if index + 1 >= len(routes) or not self._is_transport_error(exc):
                        raise
            else:
                raise ProviderError("DeepSeek route selection failed.") from last_error
        except ProviderConfigurationError:
            raise
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("DeepSeek filament color matching failed.") from exc
        try:
            if not isinstance(response_payload, dict):
                raise ValueError("DeepSeek response was not an object")
            choices = response_payload.get("choices")
            if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                raise ValueError("DeepSeek response has no choices")
            message = choices[0].get("message")
            if not isinstance(message, dict):
                raise ValueError("DeepSeek response has no message")
            content = message.get("content")
            if isinstance(content, list):
                content = "".join(
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in content
                )
            if not isinstance(content, str):
                raise ValueError("DeepSeek color response was not text")
            normalized = content.strip()
            if normalized.startswith("```"):
                normalized = normalized.removeprefix("```").removeprefix("json").removesuffix("```").strip()
            payload = json.loads(normalized)
            raw_assignments = payload if isinstance(payload, list) else ColorMatchResponse.model_validate(payload).assignments
            return [ColorMatchAssignment.model_validate(item) for item in raw_assignments]
        except Exception as exc:
            raise ProviderError("DeepSeek returned invalid filament color assignments.") from exc
