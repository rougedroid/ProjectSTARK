from neo_reasoning.compiler import compile_rules
from neo_reasoning.models import Pattern, Proposition, ReasoningAction
from neo_reasoning.workspace import Workspace
from neo_reasoning.operators import ForwardInference, BackwardChaining, HypothesisTesting
from test_operators import FakeGraph, p

RULE = {'rule_id':'rule-paid', 'reviewed':True, 'premises':[['Client','paid','fees'], ['Client','received','tranches']], 'conclusion':['Agreement','status','terminated'], 'source_id':'clause-12'}

def test_compiler_rejects_unreviewed_and_malformed():
    rules, errors = compile_rules([{**RULE, 'reviewed':False}, {'reviewed':True,'rule_id':'x','premises':[]}])
    assert not rules and len(errors)==2

def test_two_premise_forward_and_backward():
    g=FakeGraph([p('a','Client','paid','fees'),p('b','Client','received','tranches')])
    w=Workspace(goal=Pattern('Agreement','status','terminated'), metadata={'compiled_rules':[RULE]})
    f=ForwardInference().execute(g,w,ReasoningAction('forward_inference',w.goal,'test'))
    assert f['count']==1 and f['derived'][0]['rule_id']=='rule-paid'
    b=BackwardChaining().execute(g,w,ReasoningAction('backward_chaining',w.goal,'test'))
    assert b['status']=='supported' and b['proof']['rule_id']=='rule-paid'

def test_missing_premise_unknown():
    g=FakeGraph([p('a','Client','paid','fees')]); goal=Pattern('Agreement','status','terminated')
    w=Workspace(goal=goal, metadata={'compiled_rules':[RULE]})
    assert ForwardInference().execute(g,w,ReasoningAction('forward_inference',goal,'test'))['count']==0
    assert BackwardChaining().execute(g,w,ReasoningAction('backward_chaining',goal,'test'))['status']=='unknown'

def test_obligation_not_completion():
    g=FakeGraph([p('a','Provider','informed','Client',modality='obligation')])
    w=Workspace(goal=Pattern('Provider','informed','Client'))
    r=HypothesisTesting().execute(g,w,ReasoningAction('hypothesis_testing',w.goal,'test'))
    assert r['status']=='unknown' and r['qualified_fact_ids']==['a']

def test_exception_blocks():
    g=FakeGraph([p('a','Client','paid','fees'),p('b','Client','received','tranches')])
    w=Workspace(goal=Pattern('Agreement','status','terminated'), metadata={'compiled_rules':[{**RULE, 'exceptions':[['Client','under','exemption']]}]})
    assert ForwardInference().execute(g,w,ReasoningAction('forward_inference',w.goal,'test'))['count']==0
