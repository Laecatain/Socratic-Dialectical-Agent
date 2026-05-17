
"""Socratic Dialectical Agent - LangGraph (Dynamic Knowledge Flow + Multi-Turn Memory)"""

import os

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph, START

from state import DialogueState
from nodes import make_analyzer, make_socratic_ironist
from retriever_node import make_retrieve_contradiction
from web_search_node import make_web_search


def _get_threshold() -> float:
    """Similarity threshold (S_similarity), default 0.5."""
    try:
        return float(os.getenv("SIMILARITY_THRESHOLD", "0.5"))
    except ValueError:
        return 0.5


def _has_tavily_key() -> bool:
    """Check if Tavily API key is configured."""
    return bool(os.getenv("TAVILY_API_KEY", "").strip())


def route_after_analyzer(state: DialogueState) -> str:
    """Route after Analyzer: contradiction shortcut or normal retrieval.

    When the Analyzer detects a logical contradiction between the current
    input and previously admitted premises, skip the retrieval step entirely
    and route directly to the Ironist for an ambush question.
    """
    if state.get("has_contradiction", False):
        print("[ROUTE] Contradiction detected! Routing directly to Ironist (ambush mode).")
        return "Socratic_Ironist"
    return "Retriever"


def route_after_retriever(state: DialogueState) -> str:
    """Conditional route based on retrieval quality.

    After the HyDE+normalization upgrade, rag_relevance_score is now
    semantic similarity S_similarity = 1.0 - D_cosine.
    S_similarity is gte 0.5 means high-quality hit (was: D_cosine lte 0.5).

    Routes:
    - High quality (S_similarity gte threshold) - direct to Ironist
    - Low quality + Tavily available - Web_Search
    - Low quality + no Tavily - direct to Ironist (degraded)
    """
    score = state.get("rag_relevance_score", 0.0)
    threshold = _get_threshold()

    if score >= threshold:
        print(f"[ROUTE] Similarity {score:.4f} gte threshold {threshold}, direct to Ironist.")
        return "Socratic_Ironist"

    if _has_tavily_key():
        print(f"[ROUTE] Similarity {score:.4f} lt threshold {threshold}, route to Web_Search.")
        return "Web_Search"

    print(f"[ROUTE] Similarity {score:.4f} lt threshold {threshold}, no Tavily key, degraded to Ironist.")
    return "Socratic_Ironist"


def build_graph(llm: ChatOpenAI, embeddings: OpenAIEmbeddings) -> StateGraph:
    """Build and compile the Socratic dialectical graph with multi-turn memory.

    Flow:
        START → Analyzer
                  ├─ (contradiction) → Socratic_Ironist → END
                  └─ (no contradiction) → Retriever (HyDE)
                                             ├─ (good match) → Socratic_Ironist → END
                                             ├─ (poor match + Tavily) → Web_Search → Socratic_Ironist → END
                                             └─ (poor match, no Tavily) → Socratic_Ironist → END

    The graph is compiled with MemorySaver checkpointer for cross-turn state
    persistence via thread_id in config.
    """

    graph = StateGraph(DialogueState)

    graph.add_node("Analyzer", make_analyzer(llm))
    graph.add_node("Retriever", make_retrieve_contradiction(llm, embeddings))
    graph.add_node("Web_Search", make_web_search())
    graph.add_node("Socratic_Ironist", make_socratic_ironist(llm))

    graph.add_edge(START, "Analyzer")

    # After Analyzer: check for contradiction → shortcut to Ironist if found
    graph.add_conditional_edges(
        "Analyzer",
        route_after_analyzer,
        {
            "Retriever": "Retriever",
            "Socratic_Ironist": "Socratic_Ironist",
        },
    )

    graph.add_conditional_edges(
        "Retriever",
        route_after_retriever,
        {
            "Socratic_Ironist": "Socratic_Ironist",
            "Web_Search": "Web_Search",
        },
    )

    graph.add_edge("Web_Search", "Socratic_Ironist")
    graph.add_edge("Socratic_Ironist", END)

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)
