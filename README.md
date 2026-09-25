# Virtual Learning Environment

A small, single-user learning environment for asking questions about the material you choose. Add your own EPUB books, articles, or papers, then use the web interface to search and chat with a local language model grounded in that material.

## Table of contents

- [Study modes](#study-modes)
  - [Chat](#chat)
  - [Exams](#exams)
- [What you need](#what-you-need)
- [Run locally](#run-locally)
- [Run with Docker Compose](#run-with-docker-compose)
- [How it works](#how-it-works)

## What you need

- [Python](https://www.python.org/) 3.13 or later
- [uv](https://docs.astral.sh/uv/) for Python dependencies
- [Ollama](https://ollama.com/) running locally
- Node.js 22 or later and npm (for the web interface)

Docker Desktop and Docker Compose are recommended to run the backend and frontend in containers. However, you can run the frontend and backend separately if you choose to.

## Run locally

1. Clone the repository and install the Python dependencies:

   ```bash
   git clone https://github.com/noelcodesxo/virtual-learning-environment.git
   cd virtual-learning-environment
   uv sync
   ```

2. Create local configuration files from the included templates:

   ```bash
   cp .local.env.example .local.env
   cp frontend/.env.local.example frontend/.env.local
   ```

   The defaults run chat with Ollama. To enable exam generation, set `EXAM_BUILDER_ENABLED=true` and add your OpenRouter API key to `.local.env`.

3. Install and start a local model with Ollama. The default model is `qwen3:8b`:

   ```bash
   ollama pull qwen3:8b
   ollama serve
   ```

4. Add the EPUB files you want to study. You can place them in `src/resources/` before starting the app, or use the **Add EPUB** button in the Chat sidebar after it is running. Uploads are limited to 50 MB and refresh the local `index.json` search index automatically. Existing EPUB files in `src/resources/` are examples and can be replaced with your own material.

5. Start the API in one terminal:

   ```bash
   set -a
   source .local.env
   set +a
   uv run uvicorn vle.api.app:app --app-dir src --reload
   ```

6. In a second terminal, start the web interface:

   ```bash
   cd frontend
   npm ci
   npm run dev
   ```

7. Open [http://localhost:3000](http://localhost:3000) and select the local model to begin asking questions.

The API runs at [http://localhost:8000](http://localhost:8000). Set `LLM_MODEL` to use a different Ollama model, or set `OLLAMA_BASE_URL` if Ollama is available at a different address.

## Run with Docker Compose

With Ollama running on your host machine and Docker Compose installed, run:

```bash
docker compose up --watch
```

Then open [http://localhost:3000](http://localhost:3000). The compose configuration connects the backend container to Ollama on the host at `http://host.docker.internal:11434`.

## Study modes

### Chat

Use **Chat** when you want to explore your library or get help understanding a topic. It searches the local index for the passages most relevant to your question, sends those passages and your question to your local Ollama model, and shows the sources alongside its answer. This is the best mode for open-ended questions such as “Explain this concept” or “What does this book say about …?”

### Exams

Use **Exams** when you want to test your understanding of a specific source chapter. Choose a source and chapter, or describe the topic you want to be tested on. The exam builder reads the full selected chapter and generates a multiple-choice exam; after you submit it, it scores your answers and explains the correct choices.

Exam generation is optional and disabled by default. It uses OpenRouter-compatible models for chapter selection from a description, topic mapping, and final question generation, so enabling it requires `EXAM_BUILDER_ENABLED=true` and an `OPENROUTER_API_KEY`. By default, the topic map uses the same OpenRouter model as question generation (`EXAM_MODEL`). Set `EXAM_TOPIC_MAP_MODEL` to override that model. To use local Ollama for the topic map, set `EXAM_TOPIC_MAP_PROVIDER=ollama`; it uses `LLM_MODEL` and `OLLAMA_BASE_URL` by default, and `EXAM_TOPIC_MAP_MODEL` can override the local model too. Both generation calls receive every ordered excerpt from the selected chapter or complete document. If that source exceeds the configured model's context limit, generation returns a clear error and saves no exam; choose a model with a larger context window or select a shorter source. Model requests time out after five minutes by default; set `LLM_REQUEST_TIMEOUT_SECONDS` to adjust that limit.

Before generating an exam, choose one or more Bloom's taxonomy levels: remember, understand, apply, analyze, evaluate, or create. The topic-map model identifies the chapter's central, grounded topics with short source excerpts; the question-writing model receives that map, the selected levels, and the original source excerpts.

Generated exams, answers, and scores are saved locally as individual JSON files in `data/exams/`, so they remain available after restarting or rebuilding the application. The directory is excluded from Git; back it up if you want to keep your exam history. Set `EXAMS_DIR` to store it elsewhere. Docker Compose mounts `./data` into the backend container so this history also survives container rebuilds.

## How it works

The backend extracts and chunks your EPUBs, builds a local BM25 search index, retrieves the most relevant passages for each question, and sends those passages with your question to Ollama. The interface shows the answer together with its source passages so you can check the material it used.
