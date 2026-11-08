"""Typed logical IR. Natural language is retained in source_quote; this is a proposal, not verified legal truth."""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator

LogicKind = Literal["fact", "norm", "rule", "definition", "exception", "unresolved"]

class Atom(BaseModel):
    subject: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object: str = ""
    polarity: Literal["positive", "negative"] = "positive"
    modality: Literal["statement", "obligation", "prohibition", "permission", "entitlement", "representation", "definition"] = "statement"
    temporal_scope: Optional[str] = None

class Expr(BaseModel):
    op: Literal["atom", "and", "or", "not"]
    atom: Optional[Atom] = None
    args: list["Expr"] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_tree(self):
        if self.op == "atom" and (self.atom is None or self.args):
            raise ValueError("atom node requires atom and no args")
        if self.op in ("and", "or") and (len(self.args) < 2 or self.atom is not None):
            raise ValueError("and/or require two or more arguments")
        if self.op == "not" and (len(self.args) != 1 or self.atom is not None):
            raise ValueError("not requires exactly one argument")
        return self

class Logic(BaseModel):
    kind: LogicKind
    premise: Optional[Expr] = None
    conclusion: Optional[Atom] = None
    exceptions: list[Expr] = Field(default_factory=list)
    unresolved_reason: Optional[str] = None
    review_status: Literal["proposed", "approved", "rejected"] = "proposed"

    @model_validator(mode="after")
    def validate_logic(self):
        if self.kind == "rule" and (self.premise is None or self.conclusion is None):
            raise ValueError("rule requires premise and conclusion")
        if self.kind in ("fact", "norm", "definition") and self.conclusion is None:
            raise ValueError("fact/norm/definition requires conclusion")
        if self.kind == "unresolved" and not self.unresolved_reason:
            raise ValueError("unresolved requires reason")
        return self
