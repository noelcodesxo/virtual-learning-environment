"""FastAPI composition root. Route handlers live in ``vle.api.routes``."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from vle.api.routes import chat, exams, features, library
from vle.api.runtime import lifespan


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(chat.router)
    app.include_router(library.router)
    app.include_router(features.router)
    app.include_router(exams.router)
    return app


app = create_app()
