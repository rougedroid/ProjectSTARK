from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from .models import Pattern

@dataclass
class Workspace:
    goal: Pattern | None = None
    document_ids: list[str] = field(default_factory=list)
    candidate_hypotheses: list[dict[str, Any]] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    def record(self, operator: str, description: str, result: dict[str, Any]) -> None:
        self.history.append({"timestamp": datetime.now(timezone.utc).isoformat(), "operator": operator, "description": description, "result": result})
