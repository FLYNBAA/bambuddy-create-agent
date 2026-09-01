"""OpenAI-compatible image generation provider."""

from __future__ import annotations

import asyncio
import base64
import binascii
import mimetypes
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

from ..config import Settings
from ..contracts import GeneratedImage, ImageProgressCallback
from ..network import httpx_route_kwargs, proxy_route_candidates, resolve_public_http_addresses
from .exceptions import ProviderConfigurationError, ProviderError


class OpenAICompatibleImageGenerator:
    """Generate an image from text or a mandatory reference-image edit request."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._trust_env: bool | None = None

    async def generate(
        self,
        prompt: str,
        reference_image: Path | None = None,
        image_ready: ImageProgressCallback | None = None,
    ) -> list[GeneratedImage]:
        """Generate exactly four images, preserving a supplied reference input."""
        api_key = self._settings.image_api_key.get_secret_value().strip()
        if not api_key:
            raise ProviderConfigurationError(
                "Image API key is required to generate concept images."
            )

        try:
            import httpx
        except ImportError as exc:
            raise ProviderConfigurationError(
                "httpx is required for OpenAI-compatible image generation."
            ) from exc

        if reference_image is not None and not reference_image.is_file():
            raise ProviderError(
                "The supplied reference image is unavailable; image generation was not attempted."
            )

        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        base_url = self._settings.image_base_url.rstrip("/")
        trust_env = await self._select_trust_env(httpx, headers, base_url)
        timeout = httpx.Timeout(self._settings.image_timeout_seconds)
        async with httpx.AsyncClient(
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
            **httpx_route_kwargs(trust_env),
        ) as client:
            reference_content: bytes | None = None
            if reference_image is not None:
                try:
                    reference_content = await asyncio.to_thread(reference_image.read_bytes)
                except OSError as exc:
                    raise ProviderError(
                        "The supplied reference image could not be read; image generation was not attempted."
                    ) from exc
                if not reference_content:
                    raise ProviderError("The supplied reference image is empty.")

            images: list[GeneratedImage] = []
            for index in range(4):
                if reference_image is None:
                    response = await self._post_generation(client, base_url, prompt)
                else:
                    response = await self._post_edit(
                        client,
                        base_url,
                        prompt,
                        reference_image.name,
                        reference_content,
                    )
                item = self._single_image_item(self._json_response(response))
                content, media_type = await self._image_from_item(item)
                image = GeneratedImage(
                    content=content,
                    media_type=media_type,
                    revised_prompt=item.get("revised_prompt") if isinstance(item.get("revised_prompt"), str) else None,
                )
                images.append(image)
                if image_ready is not None:
                    await image_ready(index, image)

        return images

    async def _select_trust_env(
        self,
        httpx: Any,
        headers: Mapping[str, str],
        base_url: str,
    ) -> bool:
        if self._trust_env is not None:
            return self._trust_env
        last_error: Exception | None = None
        for trust_env in proxy_route_candidates(self._settings.image_proxy_mode):
            try:
                async with httpx.AsyncClient(
                    headers=dict(headers),
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
            "Image provider is unreachable through direct and configured proxy routes."
        ) from last_error

    def _image_options(self) -> dict[str, str]:
        return {
            "model": self._settings.image_model,
            "size": self._settings.image_size,
            "quality": self._settings.image_quality,
        }

    @staticmethod
    def _request_error(label: str, exc: Exception) -> ProviderError:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        if isinstance(status_code, int):
            return ProviderError(f"{label} was rejected by the image provider (HTTP {status_code}).")
        if type(exc).__name__ in {"ConnectTimeout", "ReadTimeout", "WriteTimeout", "PoolTimeout"}:
            return ProviderError(f"{label} timed out before the image provider responded.")
        return ProviderError(f"{label} failed before the image provider returned a response.")

    async def _post_generation(self, client: Any, base_url: str, prompt: str) -> Any:
        try:
            response = await client.post(
                f"{base_url}/images/generations",
                json=self._image_options() | {"prompt": prompt, "n": 1},
            )
            response.raise_for_status()
            return response
        except Exception as exc:
            raise self._request_error("Concept image generation request", exc) from exc

    async def _post_edit(
        self,
        client: Any,
        base_url: str,
        prompt: str,
        filename: str,
        content: bytes,
    ) -> Any:
        """Request one reference-conditioned concept image per provider call."""
        try:
            response = await client.post(
                f"{base_url}/images/edits",
                data=self._image_options() | {"prompt": prompt, "n": "1"},
                files={
                    "image": (filename, content, mimetypes.guess_type(filename)[0] or "application/octet-stream"),
                },
            )
            response.raise_for_status()
            return response
        except Exception as exc:
            raise self._request_error(
                "Reference-image generation request", exc
            ) from exc

    @staticmethod
    def _json_response(response: Any) -> Mapping[str, Any]:
        try:
            payload = response.json()
        except Exception as exc:
            raise ProviderError("Image generation returned an invalid response.") from exc
        if not isinstance(payload, Mapping):
            raise ProviderError("Image generation returned an invalid response.")
        return payload

    @staticmethod
    def _single_image_item(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        images = payload.get("data")
        if (
            not isinstance(images, list)
            or len(images) != 1
            or not isinstance(images[0], Mapping)
        ):
            raise ProviderError("Each concept image request must return exactly one image.")
        return images[0]

    async def _image_from_item(self, item: Mapping[str, Any]) -> tuple[bytes, str]:
        encoded = item.get("b64_json")
        if isinstance(encoded, str) and encoded:
            return self._decode_image(encoded), "image/png"

        image_url = item.get("url")
        if not isinstance(image_url, str) or not image_url:
            raise ProviderError("Image generation did not return image content.")
        return await self._download_remote_image(image_url)

    async def _download_remote_image(self, image_url: str) -> tuple[bytes, str]:
        """Download a provider URL without credentials, pinned to a validated public IP."""
        try:
            import httpx

            current_url = image_url
            timeout = httpx.Timeout(self._settings.image_timeout_seconds)
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                for _ in range(6):
                    parsed = urlsplit(current_url)
                    addresses = await asyncio.to_thread(resolve_public_http_addresses, current_url)
                    redirect_url: str | None = None
                    last_error: Exception | None = None

                    for address in addresses:
                        pinned_host = f"[{address}]" if ":" in address else address
                        port = parsed.port
                        if port is not None:
                            pinned_host = f"{pinned_host}:{port}"
                        pinned_url = urlunsplit(
                            (parsed.scheme, pinned_host, parsed.path or "/", parsed.query, "")
                        )
                        host_header = parsed.hostname or ""
                        if port is not None:
                            host_header = f"{host_header}:{port}"
                        request = client.build_request(
                            "GET",
                            pinned_url,
                            headers={"Accept": "image/*", "Host": host_header},
                        )
                        if parsed.scheme == "https":
                            request.extensions["sni_hostname"] = parsed.hostname

                        response = None
                        try:
                            response = await client.send(request, stream=True)
                            if response.is_redirect:
                                location = response.headers.get("location")
                                if not location:
                                    raise ProviderError("Generated image redirect omitted its destination.")
                                redirect_url = urljoin(current_url, location)
                                break
                            response.raise_for_status()
                            content = bytearray()
                            async for chunk in response.aiter_bytes():
                                content.extend(chunk)
                                if len(content) > self._settings.image_max_download_bytes:
                                    raise ProviderError("Generated image download exceeded the size limit.")
                            if not content:
                                raise ProviderError("Generated image download was empty.")
                            media_type = response.headers.get("content-type", "image/png").split(";", 1)[0]
                            return bytes(content), media_type
                        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                            last_error = exc
                        finally:
                            if response is not None:
                                await response.aclose()

                    if redirect_url is not None:
                        current_url = redirect_url
                        continue
                    if last_error is not None:
                        raise last_error
                    raise ProviderError("Generated image download failed for every resolved address.")
            raise ProviderError("Generated image download exceeded the redirect limit.")
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("Generated image download failed.") from exc

    @staticmethod
    def _decode_image(encoded: str) -> bytes:
        value = encoded.split(",", 1)[1] if encoded.startswith("data:") and "," in encoded else encoded
        try:
            content = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ProviderError("Image generation returned invalid base64 image content.") from exc
        if not content:
            raise ProviderError("Image generation returned empty image content.")
        return content
