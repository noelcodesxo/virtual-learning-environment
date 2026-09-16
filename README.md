# Virtual Learning Environment

A small, single-user learning environment for asking questions about the material you choose. Add your own EPUB books, articles, or papers, then use the web interface to search and chat with a local language model grounded in that material.

This project is intentionally simple: it has no accounts, shared workspaces, or hosted model dependency. Your documents and model stay on your machine.

## What you need

- [Python](https://www.python.org/) 3.13 or later
- [uv](https://docs.astral.sh/uv/) for Python dependencies
- [Ollama](https://ollama.com/) running locally
- Node.js 22 or later and npm (for the web interface)

Docker Desktop and Docker Compose are optional if you prefer to run the backend and frontend in containers.

## Run locally

1. Clone the repository and install the Python dependencies:

   ```bash
   git clone https://github.com/noelcodesxo/virtual-learning-environment.git
   cd virtual-learning-environment
   uv sync
   ```

2. Install and start a local model with Ollama. The default model is `qwen3:8b`:

   ```bash
   ollama pull qwen3:8b
   ollama serve
   ```

   If Ollama is already running as a desktop application or service, only the `ollama pull` command is needed.

3. Put the EPUB files you want to study in `src/resources/`. The backend creates or refreshes the local `index.json` search index when it starts. Existing EPUB files in that directory are examples and can be replaced with your own material.

4. Start the API in one terminal:

   ```bash
   uv run uvicorn server:app --app-dir src --reload
   ```

5. In a second terminal, start the web interface:

   ```bash
   cd frontend
   npm ci
   npm run dev
   ```

6. Open [http://localhost:3000](http://localhost:3000) and select the local model to begin asking questions.

The API runs at [http://localhost:8000](http://localhost:8000). Set `LLM_MODEL` to use a different Ollama model, or set `OLLAMA_BASE_URL` if Ollama is available at a different address.

## Run with Docker Compose

With Ollama running on your host machine and Docker Compose installed, run:

```bash
docker compose up --watch
```

Then open [http://localhost:3000](http://localhost:3000). The compose configuration connects the backend container to Ollama on the host at `http://host.docker.internal:11434`.

## How it works

The backend extracts and chunks your EPUBs, builds a local BM25 search index, retrieves the most relevant passages for each question, and sends those passages with your question to Ollama. The interface shows the answer together with its source passages so you can check the material it used.
