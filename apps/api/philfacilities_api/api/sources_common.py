"""Shared router, settings and constants for the source API route family."""

from __future__ import annotations

from fastapi import APIRouter

from ..config import get_settings

router = APIRouter(tags=["sources"])

settings = get_settings()

_MATCH_STATUSES = ("pending", "accepted", "rejected", "merged")
