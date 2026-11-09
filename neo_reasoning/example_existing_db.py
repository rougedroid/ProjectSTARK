"""Edit CONFIG, then run python example_existing_db.py. Read-only Neo4j access."""
from neo_reasoning import KnowledgeGraph, Workspace, Controller, Pattern
from neo_reasoning.operators import HypothesisTesting, ForwardInference, BackwardChaining

CONFIG = {
    'uri': 'bolt://127.0.0.1:7687',
    'username': 'neo4j',
    'password': 'CHANGE_ME',
    'database': 'neo4j',
    'document_ids': [],  # Empty = no filter
}

with KnowledgeGraph(CONFIG['uri'], CONFIG['username'], CONFIG['password'],
                    CONFIG['database'], CONFIG['document_ids']) as graph:
    graph.driver.verify_connectivity()
    print('Total visible propositions:', graph.count_facts())
    for fact in graph.facts(limit=5):
        print(fact.proposition_id, fact.pattern().as_tuple(), 'modality=', fact.modality)
    facts = graph.facts(limit=1000)
    if not facts:
        raise SystemExit('No propositions in this database/filter; check CONFIG and database name')
    selected = next((f for f in facts if f.modality in ('statement','representation','definition')
                     and not f.conditions and not f.exceptions and not f.temporal_scope), facts[0])
    goal = selected.pattern()
    print('Testing actual proposition:', selected.proposition_id, goal.as_tuple())
    workspace = Workspace(goal=goal, document_ids=CONFIG['document_ids'])
    for operator in (HypothesisTesting(), BackwardChaining(), ForwardInference()):
        from neo_reasoning.models import ReasoningAction
        result = operator.execute(graph, workspace, ReasoningAction(operator.name, goal, 'example'))
        print(operator.name, result)
    print('NOTE: direct match does not prove multi-step inference. Run pytest for controlled inference tests.')
