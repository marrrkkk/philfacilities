"""Pure identity-text helpers used by aggregation."""

from __future__ import annotations

from philfacilities_ingest.identity import address_overlap, address_tokens


def test_address_tokens_drops_stopwords_and_short_tokens() -> None:
    tokens = address_tokens("12 Mabini Street, Brgy. San Isidro")
    assert "12" not in tokens
    assert "mabini" in tokens
    assert "street" not in tokens


def test_administrative_names_are_removed_per_call() -> None:
    hierarchy = frozenset({"lucena", "quezon"})
    tokens = address_tokens(
        "Mabini Street, Lucena City, Quezon",
        administrative_names=hierarchy,
    )
    assert tokens == {"mabini"}


def test_shared_street_tokens_remain_distinctive() -> None:
    assert address_overlap("12 Mabini Street", "14 Mabini Street") == 1
    assert address_overlap("12 Mabini Street", "12 Rizal Avenue") == 0


def test_cache_matches_uncached_result() -> None:
    # Repeated calls must not leak one caller's administrative hierarchy into
    # another caller's token set.
    hierarchy = frozenset({"lucena"})
    first = address_tokens("Mabini Street, Lucena", administrative_names=hierarchy)
    second = address_tokens("Mabini Street, Lucena")
    assert first == {"mabini"}
    assert second == {"mabini", "lucena"}
