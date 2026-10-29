"""Operator scaffolds. Replace the NotImplementedError with your reasoning logic."""
from .base import ReasoningOperator
from ..models import ReasoningAction

class OperatorTemplate(ReasoningOperator):
    name = "operator_template"
    def available_actions(self, graph, workspace):
        if workspace.goal is None: return []
        return [ReasoningAction(self.name, workspace.goal, "Implement this operator", {"fact_count": float(graph.count_facts())})]
    def execute(self, graph, workspace, action):
        raise NotImplementedError("Implement reasoning in execute(); use graph.match(), graph.edges(), graph.provenance()")

class HypothesisTesting(OperatorTemplate):
    name = "hypothesis_testing"

class CounterexampleRetrieval(OperatorTemplate):
    name = "counterexample_retrieval"

class BackwardChaining(OperatorTemplate):
    name = "backward_chaining"

class ForwardInference(OperatorTemplate):
    name = "forward_inference"

class RelationComposition(OperatorTemplate):
    name = "relation_composition"

class PlanFeasibility(OperatorTemplate):
    name = "plan_feasibility"
