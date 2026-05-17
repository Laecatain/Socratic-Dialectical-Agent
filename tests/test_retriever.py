"""测试 retriever_node.py — 对抗性检索器（HyDE + score normalization）。"""

from unittest.mock import MagicMock

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from retriever_node import (
    HYDE_SYSTEM_PROMPT,
    HYDE_HUMAN_TEMPLATE,
    make_retrieve_contradiction,
)


# ---------- helpers ----------

def _fake_llm(text: str):
    def _invoke(messages, **kwargs):
        return AIMessage(content=text)
    return RunnableLambda(_invoke)


def _fake_embeddings():
    """Mock embeddings 避免 API 调用。"""
    emb = MagicMock()
    emb.embed_query.return_value = [0.1] * 128
    emb.embed_documents.return_value = [[0.1] * 128]
    return emb


def _base_state(**overrides) -> dict:
    s = {
        "user_input": "",
        "core_claim": "",
        "underlying_assumption": "",
        "matched_philosophy": "未知",
        "opponent_philosophy": "",
        "opponent_core_argument": "",
        "rag_counter_example": "",
        "rag_relevance_score": 0.0,
        "knowledge_source": "",
        "socratic_question": "",
        "turn_count": 1,
    }
    s.update(overrides)
    return s


# ---------- Factory ----------

class TestFactory:
    """make_retrieve_contradiction 工厂函数测试。"""

    def test_returns_callable(self):
        retriever = make_retrieve_contradiction(
            _fake_llm("测试"),
            _fake_embeddings(),
        )
        assert callable(retriever)


# ---------- Empty claim ----------

class TestEmptyClaim:
    """空 core_claim 处理。"""

    def test_returns_error_when_core_claim_empty(self):
        retriever = make_retrieve_contradiction(
            _fake_llm("查询词"),
            _fake_embeddings(),
        )
        state = _base_state(core_claim="")
        result = retriever(state)

        assert "No core claim" in result["rag_counter_example"] or "未提取到" in result["rag_counter_example"]

    def test_returns_error_when_core_claim_missing(self):
        retriever = make_retrieve_contradiction(
            _fake_llm("查询词"),
            _fake_embeddings(),
        )
        state = {"rag_counter_example": ""}  # no core_claim key
        result = retriever(state)

        assert "No core claim" in result["rag_counter_example"] or "未提取到" in result["rag_counter_example"]


# ---------- Prompt template ----------

class TestPromptTemplate:
    """HyDE 反事实查询词 Prompt 模板测试。"""

    def test_prompt_mentions_counter_argument(self):
        assert "counter-argument" in HYDE_SYSTEM_PROMPT or "反" in HYDE_SYSTEM_PROMPT

    def test_human_template_references_claim_fields(self):
        assert "core_claim" in HYDE_HUMAN_TEMPLATE
        assert "underlying_assumption" in HYDE_HUMAN_TEMPLATE
        assert "opponent_philosophy" in HYDE_HUMAN_TEMPLATE
        assert "opponent_core_argument" in HYDE_HUMAN_TEMPLATE
