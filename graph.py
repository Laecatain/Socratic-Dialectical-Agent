"""苏格拉底辩证智能体 — LangGraph 图构建"""

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langgraph.graph import END, StateGraph, START

from state import DialogueState
from nodes import make_analyzer, make_socratic_ironist
from retriever_node import make_retrieve_contradiction


def build_graph(llm: ChatOpenAI, embeddings: OpenAIEmbeddings) -> StateGraph:
    """构建并编译苏格拉底辩证图。

    流程: START -> Analyzer -> Retriever(Adversarial) -> Socratic_Ironist -> END

    Retriever 采用对抗性检索策略：先用 LLM 生成反事实查询词，
    再在 ChromaDB 中检索 type=counter_example 的反例。
    """

    graph = StateGraph(DialogueState)

    # 注册节点
    graph.add_node("Analyzer", make_analyzer(llm))
    graph.add_node("Retriever", make_retrieve_contradiction(llm, embeddings))
    graph.add_node("Socratic_Ironist", make_socratic_ironist(llm))

    # 定义边
    graph.add_edge(START, "Analyzer")
    graph.add_edge("Analyzer", "Retriever")
    graph.add_edge("Retriever", "Socratic_Ironist")
    graph.add_edge("Socratic_Ironist", END)

    return graph.compile()
