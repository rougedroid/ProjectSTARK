"""Conservative compilation into the existing reasoning engine's explicit triple rules.
Only approved, exception-free, positive conjunctions of statement atoms compile.
"""
from __future__ import annotations
from .schema import Logic, Expr

def compile_logic(logic: Logic) -> dict:
    if logic.review_status != "approved":
        return {"executable": False, "reason": "awaiting human approval"}
    if logic.kind != "rule" or logic.exceptions:
        return {"executable": False, "reason": "not an exception-free rule"}
    def flatten(e: Expr):
        if e.op == "atom":
            a = e.atom
            if a.polarity != "positive" or a.modality != "statement" or a.temporal_scope:
                raise ValueError("qualified premise")
            return [[a.subject, a.predicate, a.object]]
        if e.op == "and":
            return sum((flatten(x) for x in e.args), [])
        raise ValueError("unsupported boolean connective")
    try:
        premises = flatten(logic.premise)
        c = logic.conclusion
        if c.polarity != "positive" or c.modality != "statement" or c.temporal_scope:
            raise ValueError("qualified conclusion")
        return {"executable": True, "premises": premises, "conclusion": [c.subject, c.predicate, c.object]}
    except ValueError as e:
        return {"executable": False, "reason": str(e)}
