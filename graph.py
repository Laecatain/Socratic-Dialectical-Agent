"""苏格拉底辩证智能体 — LangGraph 图构建（含动态知识流路由）"""

import os

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langgraph.graph import END, StateGraph, START

from state import DialogueState
from nodes import make_analyzer, make_socratic_ironist
from retriever_node import make_retrieve_contradiction
from web_search_node import make_web_search


def _get_threshold() -> float:
    """读取相似度阈值（余弦距离），默认 0.5。"""
    try:
        return float(os.getenv("SIMILARITY_THRESHOLD", "0.5"))
    except ValueError:
        return 0.5


def _has_tavily_key() -> bool:
    """检查是否配置了 Tavily API Key。"""
    return bool(os.getenv("TAVILY_API_KEY", "").strip())


def route_after_retriever(state: DialogueState) -> str:
    """条件路由：根据 ChromaDB 检索质量决定走直接提问还是联网搜索。

    路由规则：
    - 分数达标（距离 ≤ 阈值） → Socratic_Ironist
    - 分数不达标 + 有 Tavily Key → Web_Search
    - 分数不达标 + 无 Tavily Key → Socratic_Ironist（降级）
    """
    score = state.get("rag_relevance_score", 2.0)
    threshold = _get_threshold()

    if score <= threshold:
        print(f"[ROUTE] 距离 {score:.4f} ≤ 阈值 {threshold}，直接提问。")
        return "Socratic_Ironist"

    if _has_tavily_key():
        print(f"[ROUTE] 距离 {score:.4f} > 阈值 {threshold}，路由到网络搜索。")
        return "Web_Search"

    print(f"[ROUTE] 距离 {score:.4f} > 阈值 {threshold}，但 TAVILY_API_KEY 未配置，降级直接提问。")
    return "Socratic_Ironist"


def build_graph(llm: ChatOpenAI, embeddings: OpenAIEmbeddings) -> StateGraph:
    """构建并编译苏格拉底辩证图（含动态知识流）。

    流程:
        START -> Analyzer -> Retriever
                                ├─ (达标) ──────────> Socratic_Ironist -> END
                                └─ (不达标) -> Web_Search -> Socratic_Ironist -> END

    Retriever 采用对抗性检索策略：先用 LLM 生成反事实查询词，
    再在 ChromaDB 中检索 type=counter_example 的反例，同时返回余弦距离分数。
    Web_Search 通过 Tavily API 搜索互联网反例作为补充。
    """

    graph = StateGraph(DialogueState)

    # 注册节点
    graph.add_node("Analyzer", make_analyzer(llm))
    graph.add_node("Retriever", make_retrieve_contradiction(llm, embeddings))
    graph.add_node("Web_Search", make_web_search())
    graph.add_node("Socratic_Ironist", make_socratic_ironist(llm))

    # 定义边
    graph.add_edge(START, "Analyzer")
    graph.add_edge("Analyzer", "Retriever")

    # 条件路由：Retriever → (达标) Socratic_Ironist | (不达标) Web_Search
    graph.add_conditional_edges(
        "Retriever",
        route_after_retriever,
        {
            "Socratic_Ironist": "Socratic_Ironist",
            "Web_Search": "Web_Search",
        },
    )

    # Web_Search → Socratic_Ironist → END
    graph.add_edge("Web_Search", "Socratic_Ironist")
    graph.add_edge("Socratic_Ironist", END)

    return graph.compile()
