"""Configure and run structured operators against an existing legal_graph_ingest database."""
from neo_reasoning import KnowledgeGraph, Workspace, Controller, Pattern
from neo_reasoning.operators import (
    StructuredHypothesisTesting, StructuredForwardInference,
    StructuredBackwardChaining, NormativeAnalysis,
)

CONFIG = {
    'uri': 'bolt://127.0.0.1:7687',
    'username': 'neo4j',
    'password': 'CHANGE_ME',
    'database': 'neo4j',
    'document_id': None,  # None = all documents
    'include_proposed': True,  # PREVIEW ONLY; switch False for approved-only
}


def main():
    if CONFIG['password'] == 'CHANGE_ME':
        raise SystemExit('Set CONFIG["password"] first')
    with KnowledgeGraph(CONFIG['uri'], CONFIG['username'], CONFIG['password'], database=CONFIG['database']) as graph:
        graph.driver.verify_connectivity()
        docs = [CONFIG['document_id']] if CONFIG['document_id'] else []
        facts = graph.facts(limit=5000, document_ids=docs)
        with_logic = [p for p in facts if p.logic_json]
        print('Propositions:', len(facts), 'with logic_json:', len(with_logic))
        if not with_logic:
            print('No logic_json found: ingest using updated extractor first.')
            return
        from neo_reasoning.logic_ir import load_logic
        claims, rules, issues = load_logic(with_logic)
        print('Parsed claims:', len(claims), 'rules:', len(rules), 'diagnostics:', issues[:5])
        if not claims and not rules:
            return
        chosen = claims[0] if claims else rules[0].conclusion
        ws = Workspace(goal=chosen.pattern, document_ids=docs,
                       metadata={'modality': chosen.modality, 'include_proposed': CONFIG['include_proposed']})
        ctl = Controller()
        for operator in (StructuredHypothesisTesting(), StructuredForwardInference(), StructuredBackwardChaining(), NormativeAnalysis()):
            ctl.register(operator)
        for action in ctl.actions(graph, ws):
            result = ctl.execute(graph, ws, action)
            print('\n', action.operator, result)

if __name__ == '__main__':
    main()
