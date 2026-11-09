import json
from neo_reasoning.models import Proposition, Pattern
from neo_reasoning.logic_engine import infer, evaluate
from neo_reasoning.logic_ir import parse_logic

def atom(s,p,o,modality='statement',polarity='positive'):
    return dict(subject=s,predicate=p,object=o,modality=modality,polarity=polarity)

def fact(pid, logic):
    return Proposition(pid, 'doc', logic_json=json.dumps(logic))

def expr(a): return {'op':'atom','atom':a}

def test_and_inference_and_provenance():
    facts=[fact('p1', {'kind':'fact','conclusion':atom('Client','paid','fees'),'review_status':'approved'}),
           fact('p2', {'kind':'fact','conclusion':atom('Client','received','tranches'),'review_status':'approved'}),
           fact('r1', {'kind':'rule','premise':{'op':'and','args':[expr(atom('Client','paid','fees')),expr(atom('Client','received','tranches'))]},'conclusion':atom('Agreement','status','terminated'),'review_status':'approved'})]
    result=infer(facts)
    match=evaluate(result, Pattern('Agreement','status','terminated'))
    assert match['status']=='supported'
    assert set(match['positive'][0]['sources'])=={'p1','p2','r1'}
    assert match['positive'][0]['depth']==1
    assert evaluate(infer(facts[:1]+facts[2:]), Pattern('Agreement','status','terminated'))['status']=='unknown'

def test_or_branches():
    rule={'kind':'rule','premise':{'op':'or','args':[expr(atom('Client','paid','fees')),expr(atom('Client','waived','fees'))]},'conclusion':atom('Agreement','eligible','closure'),'review_status':'approved'}
    assert evaluate(infer([fact('f',{'kind':'fact','conclusion':atom('Client','waived','fees'),'review_status':'approved'}),fact('r',rule)]),Pattern('Agreement','eligible','closure'))['status']=='supported'

def test_proposals_not_executed_by_default():
    f=fact('f', {'kind':'fact','conclusion':atom('Client','paid','fees')})
    assert infer([f])['claim_count']==0
    assert infer([f],include_proposed=True)['claim_count']==1

def test_exception_blocked():
    f=fact('f',{'kind':'fact','conclusion':atom('Client','paid','fees'),'review_status':'approved'})
    r=fact('r',{'kind':'rule','premise':expr(atom('Client','paid','fees')),'conclusion':atom('Agreement','status','terminated'),'exceptions':[expr(atom('Client','disputed','fees'))],'review_status':'approved'})
    out=infer([f,r]); assert out['blocked'] and not out['derived']

def test_norm_not_performed_fact():
    f=fact('f',{'kind':'norm','conclusion':atom('Provider','notify','Client','obligation'),'review_status':'approved'})
    out=infer([f]); assert evaluate(out,Pattern('Provider','notify','Client'))['status']=='unknown'
    assert evaluate(out,Pattern('Provider','notify','Client'),modality='obligation')['status']=='supported'

def test_not_rejected():
    r={'kind':'rule','premise':{'op':'not','args':[expr(atom('A','x','B'))]},'conclusion':atom('A','y','B'),'review_status':'approved'}
    _, rule, issue=parse_logic(r,'p'); assert rule is None and 'NOT' in issue

def test_variables():
    f=fact('f',{'kind':'fact','conclusion':atom('Alice','paid','fees'),'review_status':'approved'})
    r=fact('r',{'kind':'rule','premise':expr(atom('?x','paid','fees')),'conclusion':atom('?x','eligible','closure'),'review_status':'approved'})
    assert evaluate(infer([f,r]),Pattern('Alice','eligible','closure'))['status']=='supported'
