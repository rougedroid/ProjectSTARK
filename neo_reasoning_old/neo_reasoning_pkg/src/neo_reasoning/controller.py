"""Operator orchestration without built-in inference policy."""
from __future__ import annotations
from dataclasses import dataclass, field
from .models import ReasoningAction
from .operators.base import ReasoningOperator

@dataclass
class Controller:
    operators: dict[str, ReasoningOperator] = field(default_factory=dict)
    def register(self, operator: ReasoningOperator):
        if not operator.name: raise ValueError("operator.name is required")
        if operator.name in self.operators: raise ValueError(f"Duplicate operator: {operator.name}")
        self.operators[operator.name] = operator
    def actions(self, graph, workspace) -> list[ReasoningAction]:
        return [action for operator in self.operators.values() for action in operator.available_actions(graph, workspace)]
    def execute(self, graph, workspace, action: ReasoningAction):
        if action.operator not in self.operators: raise KeyError(action.operator)
        return self.operators[action.operator].execute(graph, workspace, action)
    def run(self, graph, workspace, selector, max_steps: int = 10):
        """selector(actions, workspace) -> ReasoningAction | None; no implicit reasoning decisions."""
        results = []
        for _ in range(max_steps):
            available = self.actions(graph, workspace)
            if not available: break
            action = selector(available, workspace)
            if action is None: break
            if action not in available: raise ValueError("Selector returned an unavailable action")
            results.append(self.execute(graph, workspace, action))
        return results
