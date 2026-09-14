# Repository Guidelines

## Project Structure & Module Organization

The Python backend lives in `src/`. It provides EPUB extraction and chunking (`chunker.py`), text normalization (`preprocessor.py`), BM25 indexing and retrieval (`indexer.py`, `retriever.py`), LLM providers (`llm_client.py`), and the FastAPI API (`server.py`). Tests are colocated as `src/*_test.py`. Source EPUBs belong in `src/resources/`; the generated root-level `index.json` is the search index. `frontend/` contains the static HTML, CSS, and vanilla JavaScript UI. `main.py` runs the command-line RAG workflow.

## Build, Test, and Development Commands

Use `uv` for Python dependencies and commands:

```bash
uv sync                                      # install project and test dependencies
uv run pytest -q                             # run the complete test suite
uv run pytest src/chunker_test.py -k merge -q # run focused tests
uv run uvicorn server:app --app-dir src --reload # serve the API on :8000
uv run python main.py "What is BM25?" --no-answer # rebuild/search without an LLM call
docker compose up --watch                     # run API (:8000) and UI (:3000), then watch local source changes
```

The frontend has no package manager or build step. When adding a frontend file, ensure `frontend/Dockerfile` explicitly copies it.

## Coding Style & Naming Conventions

Follow the existing Python style: four-space indentation, `snake_case` for functions, variables, and modules, and `PascalCase` for classes and Pydantic models. Keep backend modules small and use standard-library facilities before adding dependencies. Keep frontend code dependency-free, with camelCase JavaScript identifiers and selectors/classes that reflect their UI role. No formatter or linter is configured; preserve surrounding formatting and avoid unrelated rewrites.

## Testing Guidelines

Write pytest tests next to the code they cover using the `*_test.py` pattern and descriptive names such as `test_chat_rejects_empty_query`. Unit tests should mock networked LLM and HTTP calls, as existing tests do. Run the focused test file while iterating, then `uv run pytest -q` before submitting changes.

## Commit & Pull Request Guidelines

Use concise, imperative commit subjects consistent with history, for example `Add feature-flagged exam builder` or `Switch retrieval to BM25`. Keep commits scoped. Pull requests should explain user-visible or API changes, identify relevant configuration changes, include test results, link the issue when applicable, and attach screenshots for frontend changes.

After completing and testing a requested feature, commit only the task-related changes, push the feature branch, and open a pull request with the GitHub CLI unless the user explicitly opts out.

## Configuration & Secrets

Do not read, commit, or edit `.local.env` or other `.env` files. Document required keys and ask the maintainer to set values such as `OLLAMA_BASE_URL`, `LLM_MODEL`, `EXAM_BUILDER_ENABLED`, and provider API keys locally.
