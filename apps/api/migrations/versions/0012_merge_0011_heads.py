"""Merge the fusion-review and release-schema branches.

Revision ID: 0012_merge_0011_heads
Revises: 0011_fusion_v2_authority, 0011_release_schema_version
Create Date: 2026-11-17
"""

from __future__ import annotations

revision = "0012_merge_0011_heads"
down_revision = ("0011_fusion_v2_authority", "0011_release_schema_version")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
