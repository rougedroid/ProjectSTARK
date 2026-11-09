# neo-reasoning

Installable Python 3.10+ **read-only Neo4j reasoning framework** for the six-node contract knowledge graph schema. The package does not extract PDFs, create semantic edges, or implement reasoning algorithms. Those are deliberately separate from the operator boilerplate.

## Install

```bash
python -m pip install -e .
python -m pip install -e '.[dev]'
pytest -q
```

Configure your existing database (do not commit credentials):

```bash
export NEO4J_URI='bolt://localhost:7687'
export NEO4J_USERNAME='neo4j'
export NEO4J_PASSWORD='your-password'
export NEO4J_DATABASE='neo4j'
```

## Use

```python
from neo_reasoning import KnowledgeGraph, Workspace, Pattern, Controller
from neo_reasoning.operators import HypothesisTesting

with KnowledgeGraph.from_env(document_ids=['doc_your_hash']) as graph:
    goal = Pattern('Supplier', 'deliver', 'Equipment')
    workspace = Workspace(goal=goal, document_ids=['doc_your_hash'])
    print(graph.match(goal))
    print(graph.count_facts())
    print(graph.edges(relation='QUALIFIES'))
    controller = Controller()
    controller.register(HypothesisTesting())
    actions = controller.actions(graph, workspace)
    # HypothesisTesting.execute() intentionally raises NotImplementedError.
```

## Architecture

- `models.py`: typed `Document`, `Mention`, `Proposition`, `Entity`, `Reference`, `SemanticEdge`, `Evidence`, `Pattern`, `ReasoningAction`.
- `graph.py`: read-only Neo4j adapter; `facts`, `count_facts`, `get_fact`, `match`, `edges`, `provenance`, `documents`.
- `workspace.py`: goal, hypotheses, questions, evidence, history.
- `operators/base.py`: required two-method operator protocol.
- `operators/templates.py`: blank hypothesis testing, counterexamples, chaining, inference, relation composition and plan feasibility.
- `controller.py`: operator registration, action discovery, explicit execution, optional bounded controller loop.

### Important semantic constraints

1. `Proposition.polarity` is **not** equivalent to logical truth: negative contractual propositions can still be true assertions. The `truth` property exists only for compatibility with the toy API; avoid it for legal inference.
2. `modality`, conditions, exceptions, attribution and temporal scope matter when deciding whether propositions support or contradict one another.
3. `SUPPORTS`/`CONTRADICTS` are stored semantic edges, not necessarily logically valid proofs. Your operators must decide how to use their provenance and confidence.
4. There is no `Rule` node in the specified schema. `graph.rules()` returns an empty list intentionally. Implement rule projection from propositions and semantic edges if needed.
5. `graph.match()` supports `?variables` with equality binding, but performs exact string matching, not synonym matching or logical unification.
6. An empty document filter means **all** documents. Pass `document_ids` to avoid mixing contracts. Cross-document reasoning requires an explicit identity mapping strategy.
7. The adapter reads only; no graph mutation, inferred proposition persistence, or schema migration is included.
8. Limits on reads default to 1000 rows; increase explicitly for larger graphs.
9. `edges(direction='in')` returns edges relative to the anchor proposition; `source_id` is the anchor, not necessarily the Neo4j relationship origin. Use `direction='out'` for canonical directed semantics.

## Implement an operator

Subclass `ReasoningOperator`, provide `name`, `available_actions(graph, workspace)`, and `execute(graph, workspace, action)`. Use `graph.match(Pattern(...))`, `graph.edges(proposition_id=...)`, and `graph.provenance(proposition_id)` to inspect grounded evidence. Call `workspace.record()` to preserve execution traces.

This package intentionally supplies **infrastructure rather than a prewritten reasoning engine**.
