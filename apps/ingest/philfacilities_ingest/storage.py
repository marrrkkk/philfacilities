from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from .config import IngestSettings


class RawStoreIntegrityError(ValueError):
    """Raised when stored bytes do not match their recorded SHA-256."""


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


def _verify_sha256(content: bytes, expected: str) -> None:
    actual = hashlib.sha256(content).hexdigest()
    if actual != expected:
        raise RawStoreIntegrityError(
            f"Raw object SHA-256 mismatch: expected {expected}, got {actual}."
        )


def _atomic_write(target: Path, content: bytes) -> None:
    """Write bytes beside the target, fsync, then rename atomically."""

    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


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
        prefix = digest[:16]
        target = directory / f"{prefix}-{_safe(filename)}"
        if target.exists():
            # Never silently replace a content-addressed object with different
            # bytes. A corrupt store is surfaced, not repaired in place.
            _verify_sha256(target.read_bytes(), digest)
        else:
            _atomic_write(target, content)
        manifest = directory / f"{prefix}-manifest.json"
        if not manifest.exists():
            _atomic_write(
                manifest,
                (
                    "{\n"
                    f'  "sha256": "{digest}",\n'
                    f'  "filename": {json.dumps(filename)},\n'
                    f'  "bytes": {len(content)},\n'
                    f'  "preserved_at": "{datetime.now(UTC).isoformat()}"\n'
                    "}\n"
                ).encode(),
            )
        return StoredObject(uri=str(target), sha256=digest, size_bytes=len(content))

    def read(self, uri: str) -> bytes:
        path = Path(uri)
        content = path.read_bytes()
        manifest = path.with_name(f"{path.name.split('-', 1)[0]}-manifest.json")
        if manifest.exists():
            document = json.loads(manifest.read_text(encoding="utf-8"))
            expected = str(document.get("sha256") or "")
            expected_bytes = document.get("bytes")
            if expected:
                _verify_sha256(content, expected)
            if isinstance(expected_bytes, int) and len(content) != expected_bytes:
                raise RawStoreIntegrityError(
                    f"Raw object size mismatch for {path}: expected {expected_bytes} bytes, "
                    f"got {len(content)}."
                )
        else:
            # Legacy objects have no manifest; the filename still carries the
            # first 16 hex characters of the checksum.
            expected_prefix = path.name.split("-", 1)[0]
            actual_prefix = hashlib.sha256(content).hexdigest()[:16]
            if expected_prefix and actual_prefix != expected_prefix:
                raise RawStoreIntegrityError(f"Raw object SHA-256 prefix mismatch for {path}.")
        return content


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
        content = response["Body"].read()
        metadata = response.get("Metadata") or {}
        expected = str(metadata.get("sha256") or "")
        if expected:
            _verify_sha256(content, expected)
        return content


def build_store(settings: IngestSettings) -> RawStore:
    if settings.s3_bucket:
        return S3RawStore(settings)
    return FilesystemRawStore(settings.raw_store)
