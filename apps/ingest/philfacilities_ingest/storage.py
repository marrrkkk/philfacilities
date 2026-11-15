from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from .config import IngestSettings


@dataclass(frozen=True)
class StoredObject:
    uri: str
    sha256: str
    size_bytes: int


class RawStore(Protocol):
    def preserve(
        self, *, agency: str, dataset: str, release_label: str, filename: str, content: bytes
    ) -> StoredObject: ...

    def read(self, uri: str) -> bytes:
        """Read a previously preserved object by its stored URI."""
        ...


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")


class FilesystemRawStore:
    """Content-addressed filesystem store used for local development and tests."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def preserve(
        self, *, agency: str, dataset: str, release_label: str, filename: str, content: bytes
    ) -> StoredObject:
        digest = hashlib.sha256(content).hexdigest()
        directory = self.root / _safe(agency) / _safe(dataset) / _safe(release_label)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{digest[:16]}-{_safe(filename)}"
        if not target.exists():
            target.write_bytes(content)
        manifest = directory / f"{digest[:16]}-manifest.json"
        if not manifest.exists():
            manifest.write_text(
                "{\n"
                f'  "sha256": "{digest}",\n'
                f'  "filename": "{filename}",\n'
                f'  "bytes": {len(content)},\n'
                f'  "preserved_at": "{datetime.now(UTC).isoformat()}"\n'
                "}\n",
                encoding="utf-8",
            )
        return StoredObject(uri=str(target), sha256=digest, size_bytes=len(content))

    def read(self, uri: str) -> bytes:
        return Path(uri).read_bytes()


class S3RawStore:
    """Private S3-compatible raw store. Bucket policy is intentionally not managed here."""

    def __init__(self, settings: IngestSettings) -> None:
        import boto3

        if not settings.s3_bucket:
            raise ValueError("PHILFACILITIES_S3_BUCKET must be set for S3 storage")
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
        )

    def preserve(
        self, *, agency: str, dataset: str, release_label: str, filename: str, content: bytes
    ) -> StoredObject:
        digest = hashlib.sha256(content).hexdigest()
        key = (
            f"raw/{_safe(agency)}/{_safe(dataset)}/{_safe(release_label)}/"
            f"{digest[:16]}-{_safe(filename)}"
        )
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ContentType="application/octet-stream",
            Metadata={"sha256": digest, "original-filename": filename},
        )
        return StoredObject(uri=f"s3://{self.bucket}/{key}", sha256=digest, size_bytes=len(content))

    def read(self, uri: str) -> bytes:
        prefix = f"s3://{self.bucket}/"
        if not uri.startswith(prefix) or uri == prefix:
            raise ValueError(f"Object URI is not in the configured bucket {self.bucket!r}: {uri!r}")
        response = self.client.get_object(Bucket=self.bucket, Key=uri[len(prefix) :])
        return response["Body"].read()


def build_store(settings: IngestSettings) -> RawStore:
    if settings.s3_bucket:
        return S3RawStore(settings)
    return FilesystemRawStore(settings.raw_store)
