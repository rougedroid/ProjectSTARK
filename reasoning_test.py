
from neo_reasoning import KnowledgeGraph, Workspace, Pattern, Controller
from neo_reasoning.operators import (
    HypothesisTesting,
    CounterexampleRetrieval,
    BackwardChaining,
    ForwardInference,
    RelationComposition,
    PlanFeasibility,
)

# Replace these with values from your existing database.
DOCUMENT_ID = "doc_0ea2719887319365"
GOAL = Pattern(
    "Provider",
    "will inform the Client of the Submission Date(s) in writing before each Submission Date",
    ""
)

with KnowledgeGraph.from_env(document_ids=[DOCUMENT_ID]) as graph:

    # 1. Check connection and graph contents.
    graph.driver.verify_connectivity()
    print("Neo4j connection successful")
    print("Propositions:", graph.count_facts())

    # 2. Inspect actual propositions.
    facts = graph.facts(limit=5)
    for fact in facts:
        print(fact.proposition_id, fact.pattern().as_tuple())

    # 3. Create a reasoning workspace.
    workspace = Workspace(
        goal=GOAL,
        document_ids=[DOCUMENT_ID],
    )

    # 4. Register reasoning operators.
    controller = Controller()

    operators = [
        HypothesisTesting(),
        CounterexampleRetrieval(),
        BackwardChaining(),
        ForwardInference(),
        RelationComposition(),
        PlanFeasibility(),
    ]

    for operator in operators:
        controller.register(operator)

    # 5. Execute each available reasoning action.
    for action in controller.actions(graph, workspace):
        print("\nOPERATOR:", action.operator)

        try:
            result = controller.execute(graph, workspace, action)
            print(result)
        except Exception as exc:
            print("ERROR:", repr(exc))

    # 6. Inspect reasoning history.
    print("\nExecuted operations:", len(workspace.history))
    print("Unresolved questions:", workspace.unresolved_questions)
