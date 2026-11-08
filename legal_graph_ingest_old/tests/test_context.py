from legal_graph_ingest.extraction.context import ContextBuilder, ContextMemory, find_defined_terms
from legal_graph_ingest.extraction.segmenter import segment

TEXT = (
    '1. DEFINITIONS\n\n'
    '1.1 "Force Majeure Event" means any event beyond reasonable control.\n\n'
    '1.2 This Agreement is made between Acme Ltd (the "Supplier") and Beta Inc (the "Buyer").\n\n'
    "8.1 The Supplier shall maintain insurance coverage. The foregoing obligation shall continue until delivery."
)


def test_defined_terms_are_found_across_the_document():
    terms = find_defined_terms(TEXT)
    assert {"Force Majeure Event", "Supplier", "Buyer"} <= set(terms)


def test_context_contains_antecedents_headings_and_preceding_paragraph():
    clauses = segment(TEXT)
    memory = ContextMemory()
    memory.add_defined_terms(find_defined_terms(TEXT))
    memory.add_entity("Supplier")
    memory.add_proposition("prop_abc", "The Supplier must carry insurance.", "9")
    ctx = ContextBuilder().build(clauses[-1], memory, clauses[-2])
    rendered = ctx.render()
    assert "prop_abc" in rendered                     # stable ids for antecedents
    assert "Force Majeure Event" in rendered           # defined terms
    assert "KNOWN ENTITIES: Supplier" in rendered
    assert "PRECEDING PARAGRAPH" in rendered and "Acme Ltd" in rendered
    assert "[S2] The foregoing obligation" in rendered  # sentence boundaries


def test_antecedent_window_is_bounded():
    memory = ContextMemory()
    for i in range(30):
        memory.add_proposition(f"p{i}", f"text {i}")
    clause = segment("8.1 Some clause text here.")[0]
    ctx = ContextBuilder(max_antecedents=5).build(clause, memory)
    assert [a.id for a in ctx.antecedents] == [f"p{i}" for i in range(25, 30)]
