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

## v0.4: reasoning over legal_graph_ingest v0.2 logic_json

This remains a **separate installable package**. No import of `legal_graph_ingest` is required.
The Neo4j adapter now retains `Proposition.logic_json` and parses the exact JSON shape
produced by `legal_graph_ingest.logic.schema` (`kind`, `premise`, `conclusion`,
`exceptions`, `review_status`). The existing v0.3 operators remain available.

### Quick start

```bash
pip install -e '.[dev]'
pytest -q
python example_structured_db.py
```

Set credentials and the database in `example_structured_db.py`. The example prints the
actual number of propositions with `logic_json`; older documents may not have any.
For exploratory tests `include_proposed=True` permits unreviewed LLM proposals to be
analyzed, **not** treated as verified legal facts. The default library behavior is
approved-only.

### Operators

* `StructuredForwardInference`: fixed-point inference over approved logical atoms,
  conjunctions and disjunctions with variables, source IDs and rule IDs.
* `StructuredHypothesisTesting`: modality-specific support/refutation/conflict/unknown.
* `StructuredBackwardChaining`: goal-specific proof provenance **from forward closure**;
  not a standalone recursive backward search.
* `NormativeAnalysis`: obligation, permission, prohibition, entitlement retrieval,
  including norm conclusions derived from factual conditions.

```python
from neo_reasoning import KnowledgeGraph, Workspace, Controller, Pattern
from neo_reasoning.operators import StructuredHypothesisTesting, StructuredForwardInference

with KnowledgeGraph('bolt://localhost:7687', 'neo4j', 'PASSWORD') as graph:
    ws = Workspace(goal=Pattern('Agreement', 'status', 'terminated'),
                   metadata={'modality': 'statement'})
    controller = Controller()
    controller.register(StructuredHypothesisTesting())
    controller.register(StructuredForwardInference())
    for action in controller.actions(graph, ws):
        print(controller.execute(graph, ws, action))
```

### Trust and semantics

* `review_status='proposed'` is **excluded by default**. Set
  `workspace.metadata['include_proposed']=True` for development previews only.
* The engine never updates Neo4j; derived claims live in operator results/workspace.
* Facts, obligations, permissions and prohibitions have different modality keys;
  obligations do **not** imply that actions were performed.
* Exceptions block inference when applicability is unresolved. `NOT` expressions
  are reported as unsupported rather than silently misinterpreted.
* Time-scoped premises are blocked until a temporal evaluator exists.
* Proof provenance includes source proposition IDs and applied rule IDs.
* Rule matching is symbolic and exact; synonym resolution and entity canonicalization
  must be handled by the extractor or a separate normalization stage.
* This is **not** a general autonomous agent. `Controller.run` supports an external
  selector, but no LLM action-selection policy is bundled.
* Existing unstructured `conditions` and `exceptions` continue to be handled only
  by the legacy operators; the structured operators consume `logic_json`.
* This is a conservative prototype; live Neo4j integration and legal accuracy are
  not established by the offline unit tests.
