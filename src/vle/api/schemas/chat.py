from pydantic import BaseModel

from vle.core.config import Settings


class ChatRequest(BaseModel):
    query: str
    model: str = Settings.from_environment().default_model


class Source(BaseModel):
    book: str | None = None
    chapter: str | None = None
    section: str | None = None
    score: float


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]


class ModelsResponse(BaseModel):
    models: list[str]
