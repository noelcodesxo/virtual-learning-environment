import json
import urllib.error
import urllib.request

from fastapi import APIRouter, Depends, HTTPException

from vle.api.dependencies import index, retriever, settings
from vle.api.schemas.chat import ChatRequest, ChatResponse, ModelsResponse, Source
from vle.llm.clients import build_client
from vle.rag.prompts import build_rag_messages

router = APIRouter()


def fetch_ollama_models(base_url: str) -> list[str]:
    request = urllib.request.Request(f"{base_url.rstrip('/')}/api/tags")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.load(response)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach Ollama at {base_url}: {exc}") from exc
    return sorted(model["name"] for model in data.get("models", []))


@router.get("/models", response_model=ModelsResponse)
def list_models(app_settings=Depends(settings)):
    return ModelsResponse(models=fetch_ollama_models(app_settings.ollama_base_url))


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, app_settings=Depends(settings), current_index=Depends(index), searcher=Depends(retriever)):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")
    results = searcher.search(request.query, current_index)
    try:
        answer = build_client("ollama", request.model, base_url=app_settings.ollama_base_url).chat(
            build_rag_messages(request.query, results)
        )
    except (urllib.error.URLError, TimeoutError) as exc:
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}") from exc
    return ChatResponse(
        answer=answer,
        sources=[Source(book=result.get("book"), chapter=result.get("chapter"), section=result.get("section"), score=result["score"]) for result in results],
    )
