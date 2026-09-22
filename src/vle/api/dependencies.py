"""Shared FastAPI dependencies for route modules."""

from fastapi import HTTPException, Request


def application_state(request: Request):
    return request.app.state


def require_exam_builder(request: Request) -> None:
    if not request.app.state.exam_builder_enabled:
        raise HTTPException(status_code=404, detail="Exam builder is not enabled")
