"""HTTP auth helpers for DB-canonical write endpoints."""

from __future__ import annotations

import os
import secrets

from fastapi import HTTPException, Request


def require_bearer(request: Request) -> None:
    expected = os.environ.get("KB_API_TOKEN")
    if not expected:
        raise HTTPException(
            status_code=500,
            detail="KB_API_TOKEN env var not set; write API disabled",
        )
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="invalid bearer token")
    provided = header[len("Bearer ") :].strip()
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="invalid bearer token")
