from fastapi import HTTPException, Request


def settings(request: Request):
    return request.app.state.settings


def library(request: Request):
    return request.app.state.library


def retriever(request: Request):
    return request.app.state.retriever


def index(request: Request):
    return request.app.state.index


def exam_service(request: Request):
    return request.app.state.exam_service


def require_exam_builder(request: Request):
    if not request.app.state.settings.exam_builder_enabled:
        raise HTTPException(status_code=404, detail="Exam builder is not enabled")
