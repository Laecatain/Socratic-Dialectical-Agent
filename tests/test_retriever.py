"""测试 retriever_node.py — 对抗性检索器。"""

from unittest.mock import MagicMock

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from retriever_node import (
    COUNTER_QUERY_SYSTEM_PROMPT,
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
        "rag_counter_example": "",
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

        assert "未能提取到核心主张" in result["rag_counter_example"]

    def test_returns_error_when_core_claim_missing(self):
        retriever = make_retrieve_contradiction(
            _fake_llm("查询词"),
            _fake_embeddings(),
        )
        state = {"rag_counter_example": ""}  # no core_claim key
        result = retriever(state)

        assert "未能提取到核心主张" in result["rag_counter_example"]


# ---------- Prompt template ----------

class TestPromptTemplate:
    """反事实查询词 Prompt 模板测试。"""

    def test_prompt_mentions_counter_factual_query(self):
        assert "反事实查询词" in COUNTER_QUERY_SYSTEM_PROMPT

    def test_prompt_requires_no_prefix_or_explanation(self):
        assert "不要有任何前缀" in COUNTER_QUERY_SYSTEM_PROMPT

    def test_prompt_provides_examples(self):
        assert "示例" in COUNTER_QUERY_SYSTEM_PROMPT
        assert "富人应该多交税" in COUNTER_QUERY_SYSTEM_PROMPT
