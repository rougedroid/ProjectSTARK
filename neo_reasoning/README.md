# neo-reasoning

Read-only Neo4j proposition reasoning framework with implemented conservative operators.

## Install

```bash
pip install -e .
# optional tests
pip install -e '.[dev]'
pytest -q
```

Set `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, optionally `NEO4J_DATABASE`.

## Quick start

```python
from neo_reasoning import KnowledgeGraph, Workspace, Pattern, Controller
from neo_reasoning.operators import HypothesisTesting, BackwardChaining, ForwardInference

with KnowledgeGraph.from_env(document_ids=['doc_your_id']) as graph:
    workspace = Workspace(goal=Pattern('Supplier', 'deliver', 'Equipment'), document_ids=['doc_your_id'])
    controller = Controller()
    for op in [HypothesisTesting(), BackwardChaining(), ForwardInference()]:
        controller.register(op)
    for action in controller.actions(graph, workspace):
        print(action.operator, controller.execute(graph, workspace, action))
```

## Operators

- `HypothesisTesting`: classifies direct, **unconditional descriptive** evidence as supported/refuted/conflicted/unknown. Qualified legal norms are not converted into true/false claims.
- `CounterexampleRetrieval`: retrieves negative evidence, qualified clauses, triggered structured exceptions, and explicit CONTRADICTS annotations.
- `BackwardChaining`: recursively proves goals using explicit structured premises, depth/cycle bounds, and proof trees.
- `ForwardInference`: derives grounded patterns from explicit structured premises, with depth and result limits. Derivations stay in the workspace, not Neo4j.
- `RelationComposition`: traverses annotated semantic links; does not assume that SUPPORTS or QUALIFIES is transitive logical entailment.
- `PlanFeasibility`: checks supplied plan preconditions; does not claim that supported preconditions imply legal permissibility.

### Rule projection contract

The six-node schema has no Rule node. Only positive propositions whose `conditions` entries are **explicitly encoded** as `subject | predicate | object` can become executable rules. For example, a proposition with triple `Supplier | ship | Goods` and condition `Buyer | pay | Invoice` projects to `Buyer pays Invoice -> Supplier ships Goods` **as a symbolic relation**. This does not establish legal applicability, temporal validity, or normative satisfaction.

**Natural-language conditions are never silently parsed as executable logic.** They are reported under `unprojected_rules`. Any rule with exceptions is withheld by the inference operators, because open-world data cannot establish the absence of exceptions. This is deliberately conservative.

### Safety/coverage limitations

- Semantic relations are retrieval evidence, **not** guaranteed logical implication. No inferred edges are persisted.
- No automatic NLP, temporal arithmetic, deontic calculus, jurisdictional priority, quantified logic, defeasible legal reasoning, or contradiction resolution.
- The Neo4j facade uses bounded reads; large corpora require paginated streaming to avoid incomplete reasoning. The current operators cap retrieved facts at 5,000 and action-specific inference bounds.
- Explicit negative polarity only counts as negative descriptive evidence for unqualified `statement`, `representation`, or `definition` propositions. It is not treated as negation of a prohibition or obligation.
- Workspace is in memory. No durable checkpoints for reasoning execution.
- No automatic action selector; the Controller supports an externally supplied selector.
- Do not use this as a legal decision-maker without independent verification of source documents and derived proofs.

## v0.3: reviewed structured rule compiler and safer test path

This release adds `neo_reasoning.compiler.compile_rules`, which validates **explicit,
reviewed** structured rules. It does **not** automatically convert arbitrary
legal English into logical rules; that requires a separate extraction/review
step. Unsupported natural-language conditions are reported, not guessed.

Install: `pip install -e '.[dev]'`; test: `pytest -q`.
For a real database, edit `example_existing_db.py` and run it. The Neo4j
adapter is read-only. The example automatically selects a stored proposition.

Pass additional structured rules in `Workspace(metadata={'compiled_rules': [...]})`:

```python
{
  'rule_id': 'paid-and-received',
  'reviewed': True,
  'source_id': 'actual-clause-id',
  'premises': [
      ['Client', 'paid', 'fees'],
      ['Client', 'received', 'tranches'],
  ],
  'conclusion': ['Agreement', 'status', 'terminated'],
  'modality': 'statement',
}
```

Use the existing `ForwardInference` and `BackwardChaining` operators. The
example is illustrative; only add rules supported by the source contract.
The engine continues to withhold exception-bearing rules under open-world
uncertainty. Only factual rule modalities are executed for factual inference.
Legal obligations are not evidence of performed actions **when their modality
is correctly labeled**. If ingestion incorrectly labels an obligation as a
`statement`, this package cannot reliably repair the semantics.

Known limits: no LLM rule extraction, no automatic canonicalization of free-text
predicates, no full deontic/temporal calculus, no live Neo4j integration tests,
no autonomous planning. Rule compilation is intentionally strict. Review and
validate any rules generated by an LLM before setting `reviewed=True`.
