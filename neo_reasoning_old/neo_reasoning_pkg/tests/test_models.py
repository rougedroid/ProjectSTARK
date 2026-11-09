from neo_reasoning import Proposition, Pattern, Workspace, Controller, ReasoningAction
from neo_reasoning.operators import HypothesisTesting

def test_proposition_json():
    p = Proposition.from_neo4j({"proposition_id":"p1", "document_id":"d1", "subject":"Supplier", "predicate":"deliver", "object":"Equipment", "references_json": '[{"surface_text":"above", "kind":"proposition", "candidate_ids":["p0"], "resolved_id":null, "method":null, "confidence":null}]', "conditions":["paid"]})
    assert p.pattern() == Pattern("Supplier", "deliver", "Equipment")
    assert p.references[0].candidate_ids == ["p0"]
    assert p.conditions == ("paid",)

def test_workspace():
    w = Workspace(goal=Pattern("a", "b", "c"))
    w.record("test", "description", {"status":"unknown"})
    assert w.history[0]["result"]["status"] == "unknown"

def test_operator_scaffold():
    op = HypothesisTesting()
    assert op.name == "hypothesis_testing"
