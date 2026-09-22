"""Backward-compatible ASGI entrypoint for existing Uvicorn commands."""

from vle.api.app import app

__all__ = ["app"]
