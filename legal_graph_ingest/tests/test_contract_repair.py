import json
import pytest
from legal_graph_ingest.models.proposition import ExtractedProposition, Proposition
from legal_graph_ingest.validation.schema import parse_extraction, ValidationFailure

def payload(pred='is', obj=None, logic=None, modality='statement'):
    d={'local_id':'p1','subject':'Company','predicate':pred,'object':obj,'normalized_text':'Company is Client','modality':modality,'source_quote':'Company is Client'}
    if logic is not None: d['logic']=logic
    return d
def test_incomplete_copula_rejected():
    with pytest.raises(ValidationFailure): parse_extraction(json.dumps({'propositions':[payload()]}))
def test_objectless_allowed():
    p=ExtractedProposition.model_validate(payload('exists',None))
    assert p.object is None
def test_storage_roundtrip_logic():
    logic={'kind':'fact','review_status':'proposed','conclusion':{'subject':'Company','predicate':'is','object':'Client'}}
    p=Proposition.model_validate({**payload('is','Client',logic),'proposition_id':'p','document_id':'d','clause_key':'c'})
    props=p.to_node_props(); restored=Proposition.from_node_props(props)
    assert restored.object=='Client' and restored.logic.conclusion.object=='Client'
def test_conditional_cannot_assert_fact():
    logic={'kind':'fact','conclusion':{'subject':'Agreement','predicate':'status','object':'terminated'}}
    with pytest.raises(ValidationFailure): parse_extraction(json.dumps({'propositions':[payload('status','terminated',logic,'condition')]}))
def test_llm_cannot_approve():
    logic={'kind':'fact','review_status':'approved','conclusion':{'subject':'Company','predicate':'is','object':'Client'}}
    with pytest.raises(ValidationFailure): parse_extraction(json.dumps({'propositions':[payload('is','Client',logic)]}))

def test_revisions_do_not_overwrite_checkpoints(settings, contract_pdf):
    from legal_graph_ingest.storage.memory import InMemoryRepository
    from legal_graph_ingest.pipeline import IngestPipeline
    from legal_graph_ingest.extraction.ollama_client import OllamaExtractor
    from conftest import FakeBackend, scripted_responder
    repo=InMemoryRepository()
    pipe=IngestPipeline(settings,repo,OllamaExtractor(settings,FakeBackend(scripted_responder)))
    original=pipe.extract(contract_pdf,max_clauses=1)
    repeat=pipe.extract(contract_pdf,max_clauses=1)
    revised=pipe.extract(contract_pdf,max_clauses=1,revision='repair-001')
    assert original.document_id==repeat.document_id
    assert revised.document_id!=original.document_id
    assert original.clauses_extracted==1 and repeat.clauses_extracted==1 or repeat.clauses_skipped>=1
    assert revised.clauses_extracted==1
    assert repo.count_clauses(original.document_id).get('done',0)>=1

def test_conditional_premise_not_emitted_as_fact():
    text='If Client pays fees, Agreement terminates.'
    rule={'kind':'rule','premise':{'op':'atom','atom':{'subject':'Client','predicate':'pays','object':'fees'}},'conclusion':{'subject':'Agreement','predicate':'status','object':'terminated'}}
    a={'local_id':'p1','subject':'Agreement','predicate':'status','object':'terminated','normalized_text':text,'modality':'condition','source_quote':text,'logic':rule}
    b={'local_id':'p2','subject':'Client','predicate':'pays','object':'fees','normalized_text':'Client pays fees','modality':'statement','source_quote':text}
    with pytest.raises(ValidationFailure,match='conditional premise'):
        parse_extraction(json.dumps({'propositions':[a,b]}))
