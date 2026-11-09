from neo_reasoning.models import Pattern, Proposition, ReasoningAction, SemanticEdge
from neo_reasoning.workspace import Workspace
from neo_reasoning.operators import (HypothesisTesting, CounterexampleRetrieval, BackwardChaining,
    ForwardInference, RelationComposition, PlanFeasibility)
from neo_reasoning.reasoning import project_rules


def p(i, s, v, o, **kw):
    return Proposition(i, 'd', subject=s, predicate=v, object=o, **kw)

class FakeGraph:
    def __init__(self, facts, edges=()): self._facts, self._edges = facts, edges
    def facts(self, limit=1000, document_ids=None): return self._facts[:limit]
    def count_facts(self, document_ids=None): return len(self._facts)
    def edges(self, proposition_id=None, relation=None, direction='out', limit=1000):
        return [e for e in self._edges if (proposition_id is None or (e.source_id if direction=='out' else e.target_id)==proposition_id) and (relation is None or e.relation==relation)][:limit]

def run(op, graph, goal=Pattern('A','owns','B'), **parameters):
    w=Workspace(goal=goal)
    return op.execute(graph,w,ReasoningAction(op.name,goal,'test',parameters=parameters))

def test_hypothesis_negative_norm_not_false():
    g=FakeGraph([p('a','A','owns','B'),p('b','A','owns','B',polarity='negative',modality='prohibition')])
    r=run(HypothesisTesting(),g)
    assert r['status']=='supported' and r['qualified_fact_ids']==['b']

def test_conflict():
    g=FakeGraph([p('a','A','owns','B'),p('b','A','owns','B',polarity='negative')])
    assert run(HypothesisTesting(),g)['status']=='conflicted'

def test_rules_and_chaining():
    g=FakeGraph([p('a','A','owns','B'),p('r','A','controls','B',conditions=('A | owns | B',))])
    assert len(project_rules(g.facts())[0])==1
    assert run(ForwardInference(),g)['count']==1
    assert run(BackwardChaining(),g,Pattern('A','controls','B'))['status']=='supported'

def test_exception_blocks():
    g=FakeGraph([p('a','A','owns','B'),p('r','A','controls','B',conditions=('A | owns | B',),exceptions=('A | blocked | B',))])
    assert run(ForwardInference(),g)['count']==0
    assert run(BackwardChaining(),g,Pattern('A','controls','B'))['status']=='unknown'

def test_unstructured_conditions_not_executed():
    g=FakeGraph([p('r','A','controls','B',conditions=('if paid',))])
    assert run(ForwardInference(),g)['count']==0

def test_counterexample_and_relation():
    g=FakeGraph([p('a','A','owns','B'),p('b','A','owns','B',polarity='negative')], [SemanticEdge('a','b','CONTRADICTS')])
    assert run(CounterexampleRetrieval(),g)['count']>=2
    assert run(RelationComposition(),g)['paths']

def test_plan():
    g=FakeGraph([p('a','A','owns','B')])
    assert run(PlanFeasibility(),g,plan=[{'name':'step','requires':[['A','owns','B']]}])['status']=='preconditions_supported'
