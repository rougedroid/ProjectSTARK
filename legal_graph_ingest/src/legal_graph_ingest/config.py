"""Configuration from environment variables / .env. Nothing is hard-coded."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = ""
    ollama_timeout: float = 300.0
    max_retries: int = 3
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"
    max_clause_chars: int = 3500
    duplicate_threshold: float = 0.92
    max_llm_relation_pairs: int = 200
    min_relation_confidence: float = 0.6

    @classmethod
    def from_env(cls, dotenv: str | Path | None = ".env") -> "Settings":
        if dotenv:
            load_dotenv(dotenv)
        env = os.environ.get
        return cls(
            ollama_base_url=env("OLLAMA_BASE_URL", cls.ollama_base_url),
            ollama_model=env("OLLAMA_MODEL", ""),
            ollama_timeout=float(env("OLLAMA_TIMEOUT", cls.ollama_timeout)),
            max_retries=int(env("EXTRACTION_MAX_RETRIES", cls.max_retries)),
            neo4j_uri=env("NEO4J_URI", cls.neo4j_uri),
            neo4j_username=env("NEO4J_USERNAME", cls.neo4j_username),
            neo4j_password=env("NEO4J_PASSWORD", ""),
            neo4j_database=env("NEO4J_DATABASE", cls.neo4j_database),
            max_clause_chars=int(env("MAX_CLAUSE_CHARS", cls.max_clause_chars)),
            duplicate_threshold=float(env("DUPLICATE_THRESHOLD", cls.duplicate_threshold)),
            max_llm_relation_pairs=int(env("MAX_LLM_RELATION_PAIRS", cls.max_llm_relation_pairs)),
            min_relation_confidence=float(env("MIN_RELATION_CONFIDENCE", cls.min_relation_confidence)),
        )

    def require_model(self) -> None:
        if not self.ollama_model or self.ollama_model.startswith("<"):
            raise ConfigError("OLLAMA_MODEL is not set (e.g. OLLAMA_MODEL=llama3.1:8b).")

    def require_neo4j(self) -> None:
        if not self.neo4j_password or self.neo4j_password.startswith("<"):
            raise ConfigError("NEO4J_PASSWORD is not set.")
