import json
from neo_reasoning.models import Proposition, Pattern
from neo_reasoning.logic_engine import infer, evaluate
from neo_reasoning.compiler import compile_parser_logic
from neo_reasoning.reasoning import classify

def p(pid, logic):
    return Proposition.from_neo4j({'proposition_id':pid,'document_id':'d','subject':'Agreement','predicate':'status','object':'terminated','logic_json':json.dumps(logic)})
def atom(s,p,o,mod='statement'):
    return {'subject':s,'predicate':p,'object':o,'modality':mod}
def rule(status='approved'):
    return {'kind':'rule','review_status':status,'premise':{'op':'atom','atom':atom('Client','paid','fees')},'conclusion':atom('Agreement','status','terminated')}
def fact():
    return p('fact',{'kind':'fact','review_status':'approved','conclusion':atom('Client','paid','fees')})
def test_approved_implication_and_missing_premise():
    r=p('rule',rule())
    assert evaluate(infer([r]),Pattern('Agreement','status','terminated'))['status']=='unknown'
    assert evaluate(infer([r,fact()]),Pattern('Agreement','status','terminated'))['status']=='supported'
    assert len(compile_parser_logic([r])[0])==1
    assert classify(r)=='qualified'
def test_proposed_rejected_never_execute():
    for status in ('proposed','rejected'):
        r=p('rule',rule(status))
        assert not infer([r,fact()])['derived']
        assert not compile_parser_logic([r])[0]
def test_norm_is_not_action():
    n=p('n',{'kind':'norm','review_status':'approved','conclusion':atom('Provider','notified','Client','obligation')})
    out=infer([n])
    assert evaluate(out,Pattern('Provider','notified','Client'))['status']=='unknown'
    assert evaluate(out,Pattern('Provider','notified','Client'),modality='obligation')['status']=='supported'
def test_unsupported_is_diagnostic():
    r=rule(); r['premise']={'op':'or','args':[{'op':'atom','atom':atom('Client','paid','fees')},{'op':'atom','atom':atom('Client','waived','fees')}]}
    out=infer([p('r',r),fact()]); assert not out['derived']; assert any('disjunction' in d['reason'] for d in out['diagnostics'])
def test_logic_survives_neo4j_loading():
    raw=json.dumps(rule()); x=Proposition.from_neo4j({'proposition_id':'r','document_id':'d','logic_json':raw})
    assert x.logic_json==raw
