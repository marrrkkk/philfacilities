"""Raw store checks that do not require a database or an S3 service."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from philfacilities_ingest.storage import (
    FilesystemRawStore,
    RawStoreIntegrityError,
    S3RawStore,
)


def test_filesystem_store_preserves_and_reads_content(tmp_path):
    store = FilesystemRawStore(tmp_path)
    content = b"synthetic source bytes"

    stored = store.preserve(
        agency="psa",
        dataset="demo-psgc",
        release_label="SYNTHETIC-2026-Q3",
        filename="psgc workbook.xlsx",
        content=content,
    )

    assert stored.sha256 == hashlib.sha256(content).hexdigest()
    assert stored.size_bytes == len(content)
    assert store.read(stored.uri) == content
    assert stored.uri.endswith("psgc-workbook.xlsx")
    assert list(Path(stored.uri).parent.glob("*.tmp")) == []


def test_filesystem_store_detects_tampered_bytes(tmp_path):
    store = FilesystemRawStore(tmp_path)
    stored = store.preserve(
        agency="psa",
        dataset="demo-psgc",
        release_label="SYNTHETIC-2026-Q3",
        filename="psgc.xlsx",
        content=b"original source bytes",
    )

    Path(stored.uri).write_bytes(b"tampered source bytes")

    with pytest.raises(RawStoreIntegrityError, match="mismatch"):
        store.read(stored.uri)


def test_filesystem_store_checks_the_filename_prefix_for_legacy_objects(tmp_path):
    legacy = tmp_path / "deadbeefdeadbeef-legacy.xlsx"
    legacy.write_bytes(b"legacy bytes without a manifest")

    store = FilesystemRawStore(tmp_path)

    with pytest.raises(RawStoreIntegrityError, match="prefix mismatch"):
        store.read(str(legacy))


def test_s3_store_reads_the_configured_bucket_and_key():
    class FakeBody:
        def read(self):
            return b"s3 source bytes"

    class FakeClient:
        def __init__(self):
            self.calls = []

        def get_object(self, **kwargs):
            self.calls.append(kwargs)
            return {"Body": FakeBody()}

    store = S3RawStore.__new__(S3RawStore)
    store.bucket = "raw-bucket"
    store.client = FakeClient()

    assert store.read("s3://raw-bucket/raw/psa/demo/2026-Q3/file.xlsx") == b"s3 source bytes"
    assert store.client.calls == [{"Bucket": "raw-bucket", "Key": "raw/psa/demo/2026-Q3/file.xlsx"}]


@pytest.mark.parametrize(
    "uri",
    ["s3://other-bucket/key.xlsx", "s3://raw-bucket/", "file:///tmp/key.xlsx"],
)
def test_s3_store_read_rejects_uri_outside_the_configured_bucket(uri):
    class FakeClient:
        def get_object(self, **kwargs):  # pragma: no cover - must not be called
            raise AssertionError("get_object should not be called")

    store = S3RawStore.__new__(S3RawStore)
    store.bucket = "raw-bucket"
    store.client = FakeClient()

    with pytest.raises(ValueError, match="not in the configured bucket"):
        store.read(uri)


def test_s3_store_detects_tampered_bytes_from_object_metadata():
    class FakeBody:
        def read(self):
            return b"tampered source bytes"

    class FakeClient:
        def get_object(self, **kwargs):
            return {
                "Body": FakeBody(),
                "Metadata": {"sha256": hashlib.sha256(b"original source bytes").hexdigest()},
            }

    store = S3RawStore.__new__(S3RawStore)
    store.bucket = "raw-bucket"
    store.client = FakeClient()

    with pytest.raises(RawStoreIntegrityError, match="mismatch"):
        store.read("s3://raw-bucket/raw/psa/demo/2026-Q3/file.xlsx")
