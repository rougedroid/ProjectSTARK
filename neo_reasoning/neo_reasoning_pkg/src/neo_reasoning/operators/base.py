from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any
from ..graph import KnowledgeGraph
from ..workspace import Workspace
from ..models import ReasoningAction

class ReasoningOperator(ABC):
    name: str
    @abstractmethod
    def available_actions(self, graph: KnowledgeGraph, workspace: Workspace) -> list[ReasoningAction]: ...
    @abstractmethod
    def execute(self, graph: KnowledgeGraph, workspace: Workspace, action: ReasoningAction) -> dict[str, Any]: ...
