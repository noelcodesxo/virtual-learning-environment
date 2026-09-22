import json
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException

from vle.api.runtime import OLLAMA_BASE_URL, state
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
def list_models():
    return ModelsResponse(models=fetch_ollama_models(OLLAMA_BASE_URL))


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")

    results = state["retriever"].search(request.query, state["index"])
    messages = build_rag_messages(request.query, results)
    client = build_client("ollama", request.model, base_url=OLLAMA_BASE_URL)

    try:
        answer = client.chat(messages)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}") from exc

    sources = [
        Source(book=r.get("book"), chapter=r.get("chapter"), section=r.get("section"), score=r["score"])
        for r in results
    ]
    return ChatResponse(answer=answer, sources=sources)
