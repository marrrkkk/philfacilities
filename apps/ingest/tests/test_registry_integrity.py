"""Source-registry integrity checks.

These tests are the guardrail for the connector migration: a source may not be
added with missing identity, rights, access, attribution, or a duplicate
dataset identity. They also detect drift between the registry and the
per-source check chain that the connector work will replace.
"""

from __future__ import annotations

import inspect
import re

from philfacilities_api.rights import (
    PUBLICATION_INTERNAL_ONLY,
    normalize_rights,
    rights_allow_public,
)
from philfacilities_ingest.sources.registry import REAL_SOURCES, check_sources, source_spec


def test_registry_keys_match_their_definitions() -> None:
    assert REAL_SOURCES
    for key, source in REAL_SOURCES.items():
        assert source.key == key
        assert source.agency_code
        assert source.agency_name
        assert source.dataset_slug
        assert source.dataset_name


def test_dataset_identity_is_unique_per_agency() -> None:
    identities: dict[tuple[str, str], str] = {}
    for key, source in REAL_SOURCES.items():
        identity = (source.agency_code, source.dataset_slug)
        assert identity not in identities, (
            f"{key!r} reuses dataset identity {identity!r} from {identities[identity]!r}"
        )
        identities[identity] = key


def test_every_source_has_access_and_rights_metadata() -> None:
    for key, source in REAL_SOURCES.items():
        assert source.source_url.startswith(("https://", "http://")), key
        assert source.access_method, key
        assert source.update_pattern, key
        assert source.rights_basis, key
        # The canonical rights vocabulary must accept every registry value.
        assert normalize_rights(source.rights), key


def test_public_rights_sources_have_attribution_or_are_internal() -> None:
    missing: list[str] = []
    for key, source in REAL_SOURCES.items():
        public = rights_allow_public(normalize_rights(source.rights))
        internal = source.requested_publication_status == PUBLICATION_INTERNAL_ONLY
        if public and not internal and not source.attribution_text:
            missing.append(key)
    assert not missing, f"Public-rights sources without attribution: {sorted(missing)}"


def test_source_spec_carries_registry_rights_and_identity() -> None:
    for source in REAL_SOURCES.values():
        spec = source_spec(
            source,
            release_label="REGISTRY-INTEGRITY-TEST",
            filename="fixture.bin",
            content=b"fixture",
        )
        assert spec.agency_code == source.agency_code
        assert spec.dataset_slug == source.dataset_slug
        assert spec.dataset_name == source.dataset_name
        assert spec.source_url == source.source_url
        assert spec.redistribution_status == source.rights
        assert spec.rights_basis == source.rights_basis
        assert spec.attribution_text == source.attribution_text


def test_check_chain_special_cases_reference_registered_sources() -> None:
    """The pre-connector check chain must not name a source that does not exist."""

    source_text = inspect.getsource(check_sources)
    equality_keys = set(re.findall(r'key == "([^"]+)"', source_text))
    prefix_keys = set(re.findall(r'key\.startswith\("([^"]+)"\)', source_text))

    unknown = sorted(equality_keys - set(REAL_SOURCES))
    assert not unknown, f"check_sources references unknown source keys: {unknown}"

    for prefix in prefix_keys:
        assert any(key.startswith(prefix) for key in REAL_SOURCES), (
            f"check_sources has a {prefix!r} branch but no registered source matches"
        )


def test_catalog_covers_every_registered_source_with_a_connector() -> None:
    """Every registry source must have one definition and one connector."""

    from philfacilities_ingest.sources.catalog import (
        CONNECTOR_NAMES,
        CONNECTORS,
        SOURCES,
    )
    from philfacilities_ingest.sources.definitions import SOURCE_GROUPS

    assert set(REAL_SOURCES) == set(SOURCES) == set(CONNECTORS), (
        "registry, definitions, and connectors disagree on the source set"
    )
    for key, definition in SOURCES.items():
        connector = CONNECTORS[key]
        assert definition.key == key
        assert definition.group in SOURCE_GROUPS, key
        assert definition.connector == type(connector).__name__, key
        assert CONNECTOR_NAMES[key] == type(connector).__name__, key
        assert callable(getattr(connector, "discover", None)), key
        assert definition.rights.status, key
        assert definition.access.method, key
        assert definition.dataset.slug, key


def test_single_file_connectors_record_the_declared_source_url() -> None:
    """A custom fetcher must still carry the source URL onto the release."""

    from philfacilities_ingest.sources.catalog import CONNECTORS, SOURCES
    from philfacilities_ingest.sources.connectors.single_file import SingleFileConnector

    mismatched = []
    for key, connector in CONNECTORS.items():
        if not isinstance(connector, SingleFileConnector):
            continue
        if connector.url != SOURCES[key].access.source_url:
            mismatched.append((key, connector.url, SOURCES[key].access.source_url))
    assert not mismatched, f"connectors without the declared source URL: {mismatched}"
