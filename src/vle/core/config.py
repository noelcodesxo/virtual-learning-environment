"""Configuration with stable, repository-compatible storage defaults."""

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    resources_dir: Path
    index_path: Path
    exams_dir: Path
    exam_jobs_dir: Path
    ollama_base_url: str
    default_model: str
    exam_builder_enabled: bool
    exam_model: str
    exam_topic_map_provider: str
    exam_topic_map_model: str
    topic_map_max_attempts: int

    @classmethod
    def from_environment(cls) -> "Settings":
        repository_root = Path(__file__).resolve().parents[3]
        default_model = os.environ.get("LLM_MODEL", "qwen3:8b")
        exam_model = os.environ.get("EXAM_MODEL", "anthropic/claude-3.5-sonnet")
        topic_map_provider = os.environ.get("EXAM_TOPIC_MAP_PROVIDER", "openrouter")
        return cls(
            resources_dir=Path(os.environ.get("RESOURCES_DIR", repository_root / "src" / "resources")),
            index_path=Path(os.environ.get("INDEX_PATH", repository_root / "index.json")),
            exams_dir=Path(os.environ.get("EXAMS_DIR", repository_root / "data" / "exams")),
            exam_jobs_dir=Path(os.environ.get("EXAM_JOBS_DIR", repository_root / "data" / "exam_jobs")),
            ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
            default_model=default_model,
            exam_builder_enabled=os.environ.get("EXAM_BUILDER_ENABLED", "false").lower() == "true",
            exam_model=exam_model,
            exam_topic_map_provider=topic_map_provider,
            exam_topic_map_model=os.environ.get(
                "EXAM_TOPIC_MAP_MODEL",
                exam_model if topic_map_provider == "openrouter" else default_model,
            ),
            topic_map_max_attempts=3,
        )
