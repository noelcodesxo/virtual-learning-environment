from pydantic import BaseModel

from vle.api.runtime import DEFAULT_MODEL


class ChatRequest(BaseModel):
    query: str
    model: str = DEFAULT_MODEL


class Source(BaseModel):
    book: str | None = None
    chapter: str | None = None
    section: str | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]


class ModelsResponse(BaseModel):
    models: list[str]
