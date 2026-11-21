"""CLI demo commands.

Bodies are unchanged from the original single-module CLI; commands are
registered on the shared Typer apps by ``philfacilities_ingest.cli``.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from ..config import get_settings
from ..fixtures import (
    all_fixtures,
)
from ..pipeline import (
    run_ingestion,
    run_psgc_ingestion,
)
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


def generate_fixtures(
    output: Annotated[Path, typer.Option(help="Directory for generated fixture files.")] = Path(
        "database/fixtures/synthetic"
    ),
) -> None:
    """Write deterministic synthetic fixture files and a checksum manifest."""

    output.mkdir(parents=True, exist_ok=True)
    manifest = []
    for fixture in all_fixtures():
        target = output / fixture.name
        target.write_bytes(fixture.content)
        manifest.append(
            {
                "filename": fixture.name,
                "bytes": len(fixture.content),
                "sha256": hashlib.sha256(fixture.content).hexdigest(),
                "synthetic": True,
                "notice": "Synthetic demonstration data; not an official government release.",
            }
        )
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "purpose": "Deterministic synthetic fixtures for PhilFacilities tests and demo.",
                "files": manifest,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    typer.echo(f"Wrote {len(manifest)} synthetic fixtures to {output}")


def load_demo(
    reset: Annotated[bool, typer.Option(help="Delete existing demo facilities first.")] = False,
) -> None:
    """Load the complete synthetic demonstration dataset through the real pipeline."""

    settings = get_settings()
    engine, session = _session()
    try:
        if reset:
            _reset_demo(session)
            session.commit()
        for name, spec, adapter in demo_specs():
            typer.echo(f"→ {name}: {spec.release_label}")
            if adapter is None:
                result = run_psgc_ingestion(spec=spec, session=session, settings=settings)
            else:
                result = run_ingestion(
                    spec=spec, adapter=adapter, session=session, settings=settings
                )
            if "facilities_created" in result.stats:
                created_label = "facilities_created"
                created_count = result.stats["facilities_created"]
            else:
                created_label = "units_created"
                created_count = result.stats.get("units", 0)
            typer.echo(f"  {result.status} · {created_label}={created_count}")
            if result.issues:
                typer.echo(f"  warnings/issues: {len(result.issues)}")
        session.commit()
        typer.echo("Synthetic demo data loaded. All records are labelled is_synthetic=true.")
    finally:
        session.close()
        engine.dispose()
