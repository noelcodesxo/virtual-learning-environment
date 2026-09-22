from vle.core.templates import load_template, render_template

SYSTEM_PROMPT = render_template(
    load_template("vle.rag.prompt_templates", "chat_system.md"), allowed=set(), values={}
).strip()

NO_CONTEXT_MESSAGE = "No relevant context was found."

# bm25 is an internal ranking weight, not something the model needs to answer with.
EXCLUDED_METADATA_KEYS = {"text", "bm25"}


def build_rag_messages(query: str, chunks: list[dict]) -> list[dict[str, str]]:
    context = "\n\n".join(_format_chunk(chunk) for chunk in chunks) or NO_CONTEXT_MESSAGE
    user_content = f"Context:\n{context}\n\nQuestion: {query}"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _format_chunk(chunk: dict) -> str:
    metadata = "\n".join(
        f"{key}: {_format_value(value)}"
        for key, value in chunk.items()
        if key not in EXCLUDED_METADATA_KEYS and value is not None
    )
    return f"{metadata}\n{chunk['text']}"


def _format_value(value):
    return f"{value:.4f}" if isinstance(value, float) else value
