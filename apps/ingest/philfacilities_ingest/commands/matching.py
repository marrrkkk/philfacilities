"""CLI matching commands.

Bodies are unchanged from the original single-module CLI; commands are
registered on the shared Typer apps by ``philfacilities_ingest.cli``.
"""

from __future__ import annotations

import json
import uuid
from functools import partial
from typing import Annotated

import typer
from philfacilities_api.models import (
    MatchCandidate,
)
from sqlalchemy import func, select

from ..aggregation import consolidate_facilities, resolve_pending_match_candidates
from ..display_names import normalize_facility_display_names
from ..fusion import (
    auto_merge_exact_duplicates,
    build_attribute_fusions,
)
from ..health_refinement import (
    normalize_health_subtypes,
    refine_health_ownership,
)
from ..matching import (
    accept_match_candidate,
    generate_match_candidates,
    merge_deped_prefixed_duplicates,
    merge_match_candidate,
    reject_match_candidate,
    undo_match_merge,
)
from ..school_refinement import normalize_school_subtypes
from ..slugs import consolidate_numeric_slugs, normalize_facility_slugs
from .support import (
    SYNTHETIC_AGENCY_NAMES as SYNTHETIC_AGENCY_NAMES,
)
from .support import (
    _fixture_spec as _fixture_spec,
)
from .support import (
    _repair_agency_metadata as _repair_agency_metadata,
)
from .support import (
    _reset_demo as _reset_demo,
)
from .support import (
    _review_candidate as _review_candidate,
)
from .support import (
    _session as _session,
)
from .support import (
    demo_specs as demo_specs,
)


def auto_merge_duplicates_command(
    apply: Annotated[
        bool,
        typer.Option(
            "--apply/--dry-run",
            help="Apply the deterministic merges. The default is a dry run.",
        ),
    ] = False,
    limit: Annotated[int, typer.Option(min=1, help="Maximum candidates to consider.")] = 100,
) -> None:
    """Merge only exact normalized name + PSGC + address duplicates.

    Ambiguous candidates remain unmerged and are retried automatically when new
    evidence arrives; there is no human review gate. A merge retires the source
    facility but retains its source links and claims on the survivor.
    """

    engine, session = _session()
    try:
        stats = auto_merge_exact_duplicates(session, dry_run=not apply, limit=limit)
        if apply:
            build_attribute_fusions(session)
            session.commit()
        else:
            session.rollback()
        typer.echo(json.dumps(stats, indent=2, default=str))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


def consolidate_facilities_command(
    apply: Annotated[
        bool,
        typer.Option(
            "--apply/--dry-run",
            help="Apply the evidence-backed merges. The default is a dry run.",
        ),
    ] = False,
    limit: Annotated[
        int,
        typer.Option(min=1, help="Maximum facilities to merge in this run."),
    ] = 100,
    include_synthetic: Annotated[
        bool,
        typer.Option(help="Include synthetic demo facilities."),
    ] = False,
    facility_type: Annotated[
        str | None,
        typer.Option("--facility-type", help="Limit the pass to one facility type."),
    ] = None,
    defer_fusion: Annotated[
        bool,
        typer.Option(
            "--defer-fusion",
            help=(
                "Commit merges without rebuilding field fusions. Run the fusion "
                "command once afterwards; use this for large bulk passes."
            ),
        ),
    ] = False,
    commit_every: Annotated[
        int | None,
        typer.Option(
            "--commit-every",
            min=1,
            help=(
                "Commit after roughly this many merges so a long pass keeps its "
                "completed work. The default commits once at the end."
            ),
        ),
    ] = None,
    examples: Annotated[
        int,
        typer.Option(min=0, help="Maximum merge examples to include in the output."),
    ] = 20,
) -> None:
    """Aggregate every facility type from independent identity evidence.

    Names are compared with saint, legal-form and connector-order folding, but
    a name never decides identity by itself. A clique is merged only when every
    pair is eligible and at least one pair has a strong identity bridge: a
    shared official identifier, the same barangay, an address match, or points
    within 250 m. Cross-type and weaker pairs stay as pending match candidates.

    This handles all facility types. The DepEd prefixed-ID repair remains a
    separate deterministic step because it is an identifier rule, not a name
    similarity decision.
    """

    engine, session = _session()
    try:
        affected: set[uuid.UUID] = set()
        merged: set[uuid.UUID] = set()
        stats = consolidate_facilities(
            session,
            dry_run=not apply,
            limit=limit,
            include_synthetic=include_synthetic,
            example_limit=examples,
            affected_facility_ids=affected,
            facility_type=facility_type,
            commit_every=commit_every,
            defer_fusion=defer_fusion,
            merged_facility_ids=merged,
        )
        if apply:
            # Keep completed merges even if the derived fusion pass fails.
            session.commit()
            scoped = affected | merged
            if scoped:
                # A deferred pass rebuilds derived rows once for every surviving
                # facility and clears the stale rows left on retired duplicates.
                build_attribute_fusions(
                    session,
                    facility_ids=scoped,
                    multi_source_only=False,
                    batch_size=500,
                    release_objects=True,
                    commit_batches=True,
                )
            session.commit()
        else:
            session.rollback()
        typer.echo(json.dumps(stats, indent=2, default=str))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


def normalize_facility_slugs_command(
    apply: Annotated[
        bool,
        typer.Option(
            "--apply/--dry-run",
            help="Apply the slug renames. The default is a dry run.",
        ),
    ] = False,
    limit: Annotated[
        int,
        typer.Option(min=1, help="Maximum facility slugs to rename in this run."),
    ] = 50_000,
    facility_type: Annotated[
        str | None,
        typer.Option("--facility-type", help="Limit the pass to one facility type."),
    ] = None,
    commit_every: Annotated[
        int | None,
        typer.Option(
            "--commit-every",
            min=1,
            help=(
                "Commit completed renames in batches of this size so a large "
                "pass keeps its progress. The default commits once at the end."
            ),
        ),
    ] = None,
    examples: Annotated[
        int,
        typer.Option(min=0, help="Maximum rename examples to include in the output."),
    ] = 20,
) -> None:
    """Remove source suffixes from public facility slugs.

    ``-osm``, ``-doh``, ``-nha`` and similar suffixes describe the dataset that
    first reported a facility, not the facility itself. Every rename keeps the
    old slug as an alias so existing links continue to resolve, and records a
    change event for audit.
    """

    engine, session = _session()
    try:
        stats = normalize_facility_slugs(
            session,
            dry_run=not apply,
            limit=limit,
            facility_type=facility_type,
            example_limit=examples,
            commit_every=commit_every,
        )
        if apply:
            session.commit()
        else:
            session.rollback()
        typer.echo(json.dumps(stats, indent=2, default=str))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


def consolidate_numeric_slugs_command(
    apply: Annotated[
        bool,
        typer.Option(
            "--apply/--dry-run",
            help="Apply the slug renames. The default is a dry run.",
        ),
    ] = False,
    limit: Annotated[
        int,
        typer.Option(min=1, help="Maximum facility slugs to rename in this run."),
    ] = 50_000,
    facility_type: Annotated[
        str | None,
        typer.Option("--facility-type", help="Limit the pass to one facility type."),
    ] = None,
    commit_every: Annotated[
        int | None,
        typer.Option("--commit-every", min=1, help="Commit after roughly this many renames."),
    ] = None,
    examples: Annotated[
        int,
        typer.Option(min=0, help="Maximum rename examples to include in the output."),
    ] = 20,
) -> None:
    """Move a consolidated facility's clean base slug from a merged tombstone.

    Numbered slugs were assigned before duplicates were merged. A survivor keeps
    the numbered slug while the tombstone holds the clean one, so the clean URL
    redirects. This pass gives the clean slug to the survivor and keeps the old
    numbered slug as a bookmark alias.
    """

    engine, session = _session()
    try:
        stats = consolidate_numeric_slugs(
            session,
            dry_run=not apply,
            limit=limit,
            facility_type=facility_type,
            example_limit=examples,
            commit_every=commit_every,
        )
        if apply:
            session.commit()
        else:
            session.rollback()
        typer.echo(json.dumps(stats, indent=2, default=str))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


def normalize_display_names_command(
    apply: Annotated[
        bool,
        typer.Option(
            "--apply/--dry-run",
            help="Apply the display-name normalization. The default is a dry run.",
        ),
    ] = False,
    limit: Annotated[
        int,
        typer.Option(min=1, help="Maximum display names to normalize in this run."),
    ] = 100_000,
    commit_every: Annotated[
        int | None,
        typer.Option(
            "--commit-every",
            min=1,
            help=(
                "Commit completed batches in this size so a large pass keeps its "
                "progress. The default commits once at the end."
            ),
        ),
    ] = None,
    examples: Annotated[
        int,
        typer.Option(min=0, help="Maximum change examples to include in the output."),
    ] = 20,
) -> None:
    """Title-case display names published entirely in capitals.

    Abbreviations, Roman numerals, ordinals, single letters and consonant-only
    initialisms keep their uppercase form. The source spelling is retained in
    ``official_name``, the source payload, and the field assertions.
    """

    engine, session = _session()
    try:
        stats = normalize_facility_display_names(
            session,
            dry_run=not apply,
            limit=limit,
            example_limit=examples,
            commit_every=commit_every,
        )
        if apply:
            session.commit()
        else:
            session.rollback()
        typer.echo(json.dumps(stats, indent=2, default=str))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


def refine_health_ownership_command(
    apply: Annotated[
        bool,
        typer.Option(
            "--apply/--dry-run",
            help="Apply the ownership refinements. The default is a dry run.",
        ),
    ] = False,
    limit: Annotated[
        int,
        typer.Option(min=1, help="Maximum facilities to update in this run."),
    ] = 50_000,
    examples: Annotated[
        int,
        typer.Option(min=0, help="Maximum examples to include in the output."),
    ] = 20,
) -> None:
    """Apply the DOH NHFR ownership sub-classification.

    Only broad ``GOVERNMENT_UNSPECIFIED`` / ``PRIVATE_UNSPECIFIED`` / unknown
    values are refined, and only within the facility's existing government or
    private major class. The subclassification and DOH facility code remain on
    the health profile as evidence.
    """

    engine, session = _session()
    try:
        stats = refine_health_ownership(
            session,
            dry_run=not apply,
            limit=limit,
            example_limit=examples,
        )
        if apply:
            session.commit()
        else:
            session.rollback()
        typer.echo(json.dumps(stats, indent=2, default=str))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


def normalize_health_subtypes_command(
    apply: Annotated[
        bool,
        typer.Option(
            "--apply/--dry-run",
            help="Apply the subtype normalization. The default is a dry run.",
        ),
    ] = False,
    limit: Annotated[
        int,
        typer.Option(min=1, help="Maximum facilities to update in this run."),
    ] = 50_000,
    examples: Annotated[
        int,
        typer.Option(min=0, help="Maximum examples to include in the output."),
    ] = 20,
) -> None:
    """Replace raw accreditation labels with controlled health subtypes.

    PhilHealth benefit-package categories (``Postpartum``, ``GAMOT Package
    Providers``, ``LEVEL 1``) describe a package or a hospital level, not a
    physical facility class. Explicit facility labels are mapped; non-facility
    labels are cleared; unrecognised labels are reported and left unchanged.
    The raw value remains on the health profile and the source record.
    """

    engine, session = _session()
    try:
        stats = normalize_health_subtypes(
            session,
            dry_run=not apply,
            limit=limit,
            example_limit=examples,
        )
        if apply:
            session.commit()
        else:
            session.rollback()
        typer.echo(json.dumps(stats, indent=2, default=str))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


def normalize_school_subtypes_command(
    apply: Annotated[
        bool,
        typer.Option(
            "--apply/--dry-run",
            help="Apply the subtype normalization. The default is a dry run.",
        ),
    ] = False,
    limit: Annotated[
        int,
        typer.Option(min=1, help="Maximum facilities to update in this run."),
    ] = 50_000,
    examples: Annotated[
        int,
        typer.Option(min=0, help="Maximum examples to include in the output."),
    ] = 20,
) -> None:
    """Replace raw map tags with controlled school subtypes.

    OpenStreetMap education layers publish ``school``, ``university`` or
    ``kindergarten`` as the subtype. Explicit school labels are mapped to the
    controlled vocabulary; labels that belong to another facility category are
    cleared; unrecognised labels are reported and left unchanged. The raw tag
    remains on the source record and the facility type is never changed.
    """

    engine, session = _session()
    try:
        stats = normalize_school_subtypes(
            session,
            dry_run=not apply,
            limit=limit,
            example_limit=examples,
        )
        if apply:
            session.commit()
        else:
            session.rollback()
        typer.echo(json.dumps(stats, indent=2, default=str))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


def merge_deped_prefixed_ids_command(
    apply: Annotated[
        bool,
        typer.Option(
            "--apply/--dry-run",
            help="Apply the verified merges. The default is a dry run.",
        ),
    ] = False,
    limit: Annotated[
        int,
        typer.Option(min=1, help="Maximum merges to apply in this run."),
    ] = 1000,
) -> None:
    """Merge EBEIS seven-digit prefixed IDs into their six-digit school.

    The EBEIS result set can list the same school under its official six-digit
    BEIS ID and a seven-digit level-prefixed variant (for example 403263 and
    1403263). The prefixed row is retained as source evidence but is not a
    second real-world school. Each merge is recorded as an accepted
    ``deped_prefixed_school_id`` candidate and can be undone with
    ``match-candidates-undo-merge``.
    """

    engine, session = _session()
    try:
        affected: set[uuid.UUID] = set()
        stats = merge_deped_prefixed_duplicates(
            session,
            dry_run=not apply,
            limit=limit,
            affected_facility_ids=affected,
        )
        if apply:
            if affected:
                build_attribute_fusions(session, facility_ids=affected)
            session.commit()
        else:
            session.rollback()
        typer.echo(json.dumps(stats, indent=2, default=str))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


def match_candidates_generate() -> None:
    """Scan existing source links and queue deterministic duplicate candidates."""

    engine, session = _session()
    try:
        stats = generate_match_candidates(session)
        session.commit()
        typer.echo(json.dumps(stats, indent=2))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


def match_candidates_list(
    status: Annotated[
        str | None, typer.Option(help="pending, accepted, rejected, merged, or all")
    ] = "pending",
    limit: Annotated[int, typer.Option(min=1, max=500)] = 50,
) -> None:
    """List identity-match candidates and their automatic match state."""

    engine, session = _session()
    try:
        query = select(MatchCandidate).order_by(MatchCandidate.created_at.desc()).limit(limit)
        if status and status != "all":
            query = query.where(MatchCandidate.match_status == status)
        rows = session.scalars(query).all()
        counts = dict(
            session.execute(
                select(MatchCandidate.match_status, func.count()).group_by(
                    MatchCandidate.match_status
                )
            ).all()
        )
        typer.echo(
            "counts="
            + json.dumps(
                {key: counts.get(key, 0) for key in ("pending", "accepted", "rejected", "merged")}
            )
        )
        if not rows:
            typer.echo("No match candidates.")
            return
        for row in rows:
            typer.echo(
                f"{row.id} {row.match_status} confidence={float(row.match_confidence):.3f} "
                f"{row.source_agency_code}:{row.source_facility_id} -> "
                f"{row.candidate_agency_code}:{row.candidate_facility_id}"
            )
    finally:
        session.close()
        engine.dispose()


def match_candidates_resolve(
    apply: Annotated[
        bool,
        typer.Option(
            "--apply/--dry-run",
            help="Apply the resolutions. The default is a dry run.",
        ),
    ] = False,
    limit: Annotated[
        int,
        typer.Option(min=1, help="Maximum pending candidates to resolve in this run."),
    ] = 10_000,
    reviewer: Annotated[
        str,
        typer.Option(help="Reviewer recorded on automatic merges and rejections."),
    ] = "system:match-candidate-resolution",
    examples: Annotated[
        int,
        typer.Option(min=0, help="Maximum resolution examples to include in the output."),
    ] = 20,
) -> None:
    """Resolve every pending candidate against current evidence.

    A stale, cross-type, conflicting or weak pair is rejected and kept as
    audit history so it is not queued again. A pair that still meets the
    automatic consolidation rule is merged into its candidate target.
    """

    engine, session = _session()
    try:
        stats = resolve_pending_match_candidates(
            session,
            dry_run=not apply,
            limit=limit,
            reviewer=reviewer,
            example_limit=examples,
        )
        if apply:
            session.commit()
        else:
            session.rollback()
        typer.echo(json.dumps(stats, indent=2, default=str))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


def match_candidates_accept(
    candidate_id: uuid.UUID,
    reviewer: Annotated[str, typer.Option(help="Reviewer name or role identifier.")],
    note: Annotated[str | None, typer.Option(help="Reason for the decision.")] = None,
) -> None:
    """Confirm a candidate as the same facility. Merging is a separate explicit step."""

    _review_candidate(accept_match_candidate, candidate_id, reviewer, note)


def match_candidates_reject(
    candidate_id: uuid.UUID,
    reviewer: Annotated[str, typer.Option(help="Reviewer name or role identifier.")],
    note: Annotated[str | None, typer.Option(help="Reason for the decision.")] = None,
) -> None:
    """Reject a candidate and retain it so the pair is not re-queued."""

    _review_candidate(reject_match_candidate, candidate_id, reviewer, note)


def match_candidates_merge(
    candidate_id: uuid.UUID,
    reviewer: Annotated[str, typer.Option(help="Reviewer name or role identifier.")],
    note: Annotated[str | None, typer.Option(help="Reason for the merge.")] = None,
    allow_facility_type_mismatch: Annotated[
        bool,
        typer.Option(
            "--allow-facility-type-mismatch",
            help=(
                "Explicitly merge a reviewed cross-type candidate. The surviving "
                "facility keeps its own type."
            ),
        ),
    ] = False,
) -> None:
    """Apply an accepted candidate: retire the source facility into the candidate facility."""

    _review_candidate(
        partial(
            merge_match_candidate,
            allow_facility_type_mismatch=allow_facility_type_mismatch,
        ),
        candidate_id,
        reviewer,
        note,
    )


def match_candidates_undo_merge(
    candidate_id: uuid.UUID,
    reviewer: Annotated[str, typer.Option(help="Reviewer name or role identifier.")],
    note: Annotated[str | None, typer.Option(help="Reason for undoing the merge.")] = None,
) -> None:
    """Undo a merge and restore the source facility and its linked evidence."""

    _review_candidate(undo_match_merge, candidate_id, reviewer, note)
