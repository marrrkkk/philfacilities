from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class IngestSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PHILFACILITIES_", env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+psycopg://philfacilities:philfacilities@localhost:54329/philfacilities"
    )
    raw_store: Path = Path("var/raw")
    report_dir: Path = Path("var/reports")
    s3_endpoint: str | None = None
    s3_bucket: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    source_contact: str = "data@philfacilities.local"
    # Optional operator-supplied webhook for actionable source-check failures.
    # No vendor or channel is assumed; leave unset to disable outbound alerts.
    alert_webhook_url: str | None = None


@lru_cache
def get_settings() -> IngestSettings:
    return IngestSettings()
