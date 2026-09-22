"""Configuration with stable, repository-compatible storage defaults."""

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    resources_dir: Path
    index_path: Path
    exams_dir: Path
    ollama_base_url: str
    default_model: str
    exam_builder_enabled: bool
    exam_model: str

    @classmethod
    def from_environment(cls) -> "Settings":
        repository_root = Path(__file__).resolve().parents[3]
        return cls(
            resources_dir=repository_root / "src" / "resources",
            index_path=Path(os.environ.get("INDEX_PATH", repository_root / "index.json")),
            exams_dir=Path(os.environ.get("EXAMS_DIR", repository_root / "data" / "exams")),
            ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
            default_model=os.environ.get("LLM_MODEL", "qwen3:8b"),
            exam_builder_enabled=os.environ.get("EXAM_BUILDER_ENABLED", "false").lower() == "true",
            exam_model=os.environ.get("EXAM_MODEL", "anthropic/claude-3.5-sonnet"),
        )
