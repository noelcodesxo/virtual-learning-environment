"""Supabase bearer-token verification for protected API endpoints."""

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from fastapi import Header, HTTPException


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str | None = None


def require_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")

    url = os.environ.get("SUPABASE_URL")
    anon_key = os.environ.get("SUPABASE_ANON_KEY")
    if not url or not anon_key:
        raise HTTPException(status_code=503, detail="Authentication is not configured")

    request = urllib.request.Request(
        f"{url.rstrip('/')}/auth/v1/user",
        headers={"apikey": anon_key, "Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise HTTPException(status_code=401, detail="Invalid or expired session") from exc
        raise HTTPException(status_code=503, detail="Authentication service is unavailable") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise HTTPException(status_code=503, detail="Authentication service is unavailable") from exc

    user_id = data.get("id")
    if not isinstance(user_id, str):
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return CurrentUser(id=user_id, email=data.get("email"))
