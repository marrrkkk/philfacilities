from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime

from fastapi import Request

from .errors import ApiError


def encode_cursor(updated_at: datetime, facility_id: uuid.UUID) -> str:
    payload = {"updated_at": updated_at.astimezone(UTC).isoformat(), "id": str(facility_id)}
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    if len(cursor) > 512:
        raise ApiError(400, "invalid_cursor", "The pagination cursor is invalid.")
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        updated_at = datetime.fromisoformat(payload["updated_at"])
        facility_id = uuid.UUID(payload["id"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ApiError(400, "invalid_cursor", "The pagination cursor is invalid.") from exc
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)
    return updated_at, facility_id


def request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def clamp_limit(limit: int, maximum: int, default: int) -> int:
    if limit < 1:
        raise ApiError(400, "invalid_limit", "limit must be at least 1.")
    return min(limit, maximum) if limit else default
