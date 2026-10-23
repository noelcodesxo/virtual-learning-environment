FROM python:3.13.17-slim-trixie@sha256:fe14fd57a4c0361110eaa0c284112b189750bcb43fb04bb5d1ee7b7744027ccf

WORKDIR /app

RUN pip install --no-cache-dir uv==0.12.10

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "vle.api.app:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
