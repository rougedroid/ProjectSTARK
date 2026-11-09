import json
from legal_graph_ingest import GraphIngestor
from legal_graph_ingest.logic.schema import Logic
from legal_graph_ingest.logic.compiler import compile_logic

class Backend:
    def chat(self, **kwargs):
        text = 'If the Client pays all outstanding fees, the Client becomes eligible for closure.'
        return {'message': {'content': json.dumps({'propositions':[{
            'local_id':'p1','subject':'Client','predicate':'eligible for','object':'closure',
            'normalized_text':text,'modality':'condition','source_quote':text,
            'logic':{'kind':'rule','premise':{'op':'atom','atom':{'subject':'Client','predicate':'pays','object':'all outstanding fees'}},
            'conclusion':{'subject':'Client','predicate':'eligible for','object':'closure'}}
        }]})}}

def test_manual_insert_idempotent_and_provenance():
    with GraphIngestor(in_memory=True, ollama_model='test', ollama_backend=Backend()) as g:
        txt='If the Client pays all outstanding fees, the Client becomes eligible for closure.'
        first=g.add_rule(txt)
        second=g.add_rule(txt)
        assert len(first)==len(second)==1
        assert first[0].proposition_id==second[0].proposition_id
        assert len(g.propositions(first[0].document_id))==1
        assert first[0].attribution=='user_input'
        assert g.mentions(first[0].document_id)[0].page_start==1  # virtual page; marked user_input
        assert first[0].logic.kind=='rule'
        assert compile_logic(first[0].logic)['executable'] is False
        approved=first[0].logic.model_copy(update={'review_status':'approved'})
        assert compile_logic(approved)['executable'] is True

def test_invalid_rule_and_unknown_document():
    with GraphIngestor(in_memory=True, ollama_model='test', ollama_backend=Backend()) as g:
        import pytest
        with pytest.raises(ValueError): g.add_rule(' ')
        with pytest.raises(ValueError): g.add_rule('Something',document_id='missing')

def test_exception_blocks_compilation():
    l=Logic.model_validate({'kind':'rule','review_status':'approved',
        'premise':{'op':'atom','atom':{'subject':'A','predicate':'p','object':'B'}},
        'conclusion':{'subject':'C','predicate':'q','object':'D'},
        'exceptions':[{'op':'atom','atom':{'subject':'X','predicate':'r','object':'Y'}}]})
    assert not compile_logic(l)['executable']
