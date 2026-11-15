from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PHILFACILITIES_", env_file=".env", extra="ignore")

    env: str = "local"
    database_url: str = (
        "postgresql+psycopg://philfacilities:philfacilities@localhost:54329/philfacilities"
    )
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    rate_limit_per_minute: int = 120
    max_page_size: int = 100
    default_page_size: int = 20
    max_bbox_area_deg2: float = 25.0
    max_nearby_radius_m: int = 50_000
    max_map_features: int = 500
    api_version: str = "v1"
    coverage_stale_after_days: int = 365

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
