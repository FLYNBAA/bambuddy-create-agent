"""Environment-backed application settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    app_name: str = "3D Print Agent"
    app_host: str = "127.0.0.1"
    app_port: int = 8765
    app_public_base_url: str = "http://127.0.0.1:8765"
    allowed_origins: str = "http://127.0.0.1:8765,http://localhost:8765"
    forwarded_allow_ips: str = "127.0.0.1"

    data_dir: Path = _BACKEND_DIR / "data"
    max_upload_bytes: int = 8 * 1024 * 1024
    max_upload_pixels: int = 20_000_000
    filament_database_url: SecretStr = Field(default=SecretStr(""))

    deepseek_api_key: SecretStr = Field(default=SecretStr(""))
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_timeout_seconds: float = 60.0
    deepseek_proxy_mode: Literal["auto", "direct", "environment"] = "auto"

    image_api_key: SecretStr = Field(default=SecretStr(""))
    image_base_url: str = "https://api.yunma.ai/v1"
    image_model: str = "gpt-image-2"
    image_size: str = "1024x1024"
    image_quality: str = "high"
    image_timeout_seconds: float = 240.0
    image_max_download_bytes: int = 32 * 1024 * 1024
    image_proxy_mode: Literal["auto", "direct", "environment"] = "auto"

    tencent_secret_id: SecretStr = Field(default=SecretStr(""))
    tencent_secret_key: SecretStr = Field(default=SecretStr(""))
    tencent_region: str = "ap-guangzhou"
    hunyuan_face_count: int = 500_000
    hunyuan_enable_pbr: bool = True
    hunyuan_poll_interval_seconds: float = 3.0
    hunyuan_timeout_seconds: float = 900.0
    hunyuan_query_failure_limit: int = 5

    meshy_api_key: SecretStr = Field(default=SecretStr(""))
    meshy_base_url: str = "https://api.meshy.ai"
    meshy_model_input_mode: str = "data_uri"
    meshy_poll_interval_seconds: float = 3.0
    meshy_timeout_seconds: float = 900.0
    meshy_max_download_bytes: int = 512 * 1024 * 1024
    meshy_proxy_mode: Literal["auto", "direct", "environment"] = "auto"
    meshy_max_uncompressed_3mf_bytes: int = 512 * 1024 * 1024

    def ensure_directories(self) -> None:
        for path in (
            self.data_dir,
            self.data_dir / "uploads",
            self.data_dir / "images",
            self.data_dir / "models",
            self.data_dir / "repaired-models",
            self.data_dir / "print-files",
        ):
            path.mkdir(parents=True, exist_ok=True)

    @property
    def origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
