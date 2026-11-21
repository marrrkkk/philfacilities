"""Command-line entry point for PhilFacilities.

The command bodies live in :mod:`philfacilities_ingest.commands`; this module
owns the Typer applications and registers every command in its original order
so ``--help`` output is unchanged. Shared helpers and ``load_demo``,
``demo_specs`` and ``_session`` are re-exported for existing importers.
"""

from __future__ import annotations

import typer

from .commands.demo import generate_fixtures as generate_fixtures
from .commands.demo import load_demo as load_demo
from .commands.discovery import crawl_public_sources as crawl_public_sources
from .commands.discovery import discover_sources as discover_sources
from .commands.discovery import probe_sources_command as probe_sources_command
from .commands.discovery import validate_lgu_inventory_command as validate_lgu_inventory_command
from .commands.matching import auto_merge_duplicates_command as auto_merge_duplicates_command
from .commands.matching import consolidate_facilities_command as consolidate_facilities_command
from .commands.matching import (
    consolidate_numeric_slugs_command as consolidate_numeric_slugs_command,
)
from .commands.matching import match_candidates_accept as match_candidates_accept
from .commands.matching import match_candidates_generate as match_candidates_generate
from .commands.matching import match_candidates_list as match_candidates_list
from .commands.matching import match_candidates_merge as match_candidates_merge
from .commands.matching import match_candidates_reject as match_candidates_reject
from .commands.matching import match_candidates_resolve as match_candidates_resolve
from .commands.matching import match_candidates_undo_merge as match_candidates_undo_merge
from .commands.matching import merge_deped_prefixed_ids_command as merge_deped_prefixed_ids_command
from .commands.matching import normalize_display_names_command as normalize_display_names_command
from .commands.matching import normalize_facility_slugs_command as normalize_facility_slugs_command
from .commands.matching import (
    normalize_health_subtypes_command as normalize_health_subtypes_command,
)
from .commands.matching import (
    normalize_school_subtypes_command as normalize_school_subtypes_command,
)
from .commands.matching import refine_health_ownership_command as refine_health_ownership_command
from .commands.pipeline import backfill_assertions_command as backfill_assertions_command
from .commands.pipeline import fill_location_psgc_command as fill_location_psgc_command
from .commands.pipeline import (
    fill_location_psgc_from_map_command as fill_location_psgc_from_map_command,
)
from .commands.pipeline import fill_locations_from_osm_command as fill_locations_from_osm_command
from .commands.pipeline import fuse_attributes_command as fuse_attributes_command
from .commands.pipeline import fusion_report_command as fusion_report_command
from .commands.pipeline import import_osm_boundaries_command as import_osm_boundaries_command
from .commands.pipeline import ingest_file as ingest_file
from .commands.releases import (
    apply_publication_decisions_command as apply_publication_decisions_command,
)
from .commands.releases import compare_releases_command as compare_releases_command
from .commands.releases import monitoring as monitoring
from .commands.releases import purge_synthetic as purge_synthetic
from .commands.releases import release_manifest_command as release_manifest_command
from .commands.releases import release_notes_command as release_notes_command
from .commands.releases import release_rollback_command as release_rollback_command
from .commands.releases import source_review_command as source_review_command
from .commands.reports import rebuild_report_command as rebuild_report_command
from .commands.reports import source_candidates_command as source_candidates_command
from .commands.reports import source_inventory_command as source_inventory_command
from .commands.reports import source_report_command as source_report_command
from .commands.reports import status as status
from .commands.source import source_check as source_check
from .commands.source import source_list as source_list
from .commands.source import source_replay as source_replay
from .commands.source import source_run as source_run
from .commands.source import source_validate as source_validate
from .commands.support import (
    SYNTHETIC_AGENCY_NAMES as SYNTHETIC_AGENCY_NAMES,
)
from .commands.support import (
    _fixture_spec as _fixture_spec,
)
from .commands.support import (
    _repair_agency_metadata as _repair_agency_metadata,
)
from .commands.support import (
    _reset_demo as _reset_demo,
)
from .commands.support import (
    _review_candidate as _review_candidate,
)
from .commands.support import (
    _session as _session,
)
from .commands.support import (
    demo_specs as demo_specs,
)

app = typer.Typer(
    add_completion=False,
    help="Source acquisition, repeatable ingestion, reports, and status for PhilFacilities.",
)
source_app = typer.Typer(add_completion=False, help="List, check, run, and validate sources.")
demo_app = typer.Typer(add_completion=False, help="Synthetic demonstration data.")
app.add_typer(source_app, name="source")
app.add_typer(demo_app, name="demo")

_REGISTRATIONS = (
    ("app", "generate-fixtures", generate_fixtures),
    ("demo_app", "load", load_demo),
    ("source_app", "list", source_list),
    ("source_app", "check", source_check),
    ("source_app", "run", source_run),
    ("source_app", "validate", source_validate),
    ("source_app", "replay", source_replay),
    ("app", "ingest-file", ingest_file),
    ("app", "fuse-attributes", fuse_attributes_command),
    ("app", "fusion-report", fusion_report_command),
    ("app", "fill-locations-from-osm", fill_locations_from_osm_command),
    ("app", "fill-location-psgc", fill_location_psgc_command),
    ("app", "fill-location-psgc-from-map", fill_location_psgc_from_map_command),
    ("app", "import-osm-boundaries", import_osm_boundaries_command),
    ("app", "auto-merge-duplicates", auto_merge_duplicates_command),
    ("app", "consolidate-facilities", consolidate_facilities_command),
    ("app", "normalize-facility-slugs", normalize_facility_slugs_command),
    ("app", "consolidate-numeric-slugs", consolidate_numeric_slugs_command),
    ("app", "normalize-display-names", normalize_display_names_command),
    ("app", "refine-health-ownership", refine_health_ownership_command),
    ("app", "normalize-health-subtypes", normalize_health_subtypes_command),
    ("app", "normalize-school-subtypes", normalize_school_subtypes_command),
    ("app", "merge-deped-prefixed-ids", merge_deped_prefixed_ids_command),
    ("app", "status", status),
    ("app", "source-candidates", source_candidates_command),
    ("app", "source-inventory", source_inventory_command),
    ("app", "source-report", source_report_command),
    ("app", "rebuild-report", rebuild_report_command),
    ("app", "probe-sources", probe_sources_command),
    ("app", "validate-lgu-inventory", validate_lgu_inventory_command),
    ("app", "backfill-assertions", backfill_assertions_command),
    ("app", "match-candidates-generate", match_candidates_generate),
    ("app", "match-candidates", match_candidates_list),
    ("app", "match-candidates-resolve", match_candidates_resolve),
    ("app", "match-candidates-accept", match_candidates_accept),
    ("app", "match-candidates-reject", match_candidates_reject),
    ("app", "match-candidates-merge", match_candidates_merge),
    ("app", "match-candidates-undo-merge", match_candidates_undo_merge),
    ("app", "apply-publication-decisions", apply_publication_decisions_command),
    ("app", "monitoring", monitoring),
    ("app", "source-review", source_review_command),
    ("app", "compare-releases", compare_releases_command),
    ("app", "release-manifest", release_manifest_command),
    ("app", "release-notes", release_notes_command),
    ("app", "release-rollback", release_rollback_command),
    ("app", "crawl", crawl_public_sources),
    ("app", "discover-sources", discover_sources),
    ("app", "purge-synthetic", purge_synthetic),
)


def _register_commands() -> None:
    apps = {"app": app, "source_app": source_app, "demo_app": demo_app}
    for target, name, func in _REGISTRATIONS:
        apps[target].command(name)(func)


_register_commands()
