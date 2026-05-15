"""测试 nodes.py — Analyzer 和 Socratic_Ironist（仍被 graph.py 使用）。"""

import json

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from nodes import make_analyzer, make_socratic_ironist


# ---------- helpers ----------

def _fake_llm(text: str):
    """构造一个返回指定 AIMessage 的 LangChain Runnable。"""
    def _invoke(messages, **kwargs):
        return AIMessage(content=text)
    return RunnableLambda(_invoke)


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


# ---------- Analyzer ----------

class TestAnalyzer:
    """Analyzer 节点的 JSON 解析逻辑。"""

    def test_parses_clean_json(self):
        analyzer = make_analyzer(_fake_llm(json.dumps({
            "core_claim": "努力就应成功",
            "underlying_assumption": "社会是公平的竞技场",
            "matched_philosophy": "程序正义",
        })))
        result = analyzer(_base_state(user_input="只要努力就能成功"))

        assert result["core_claim"] == "努力就应成功"
        assert result["underlying_assumption"] == "社会是公平的竞技场"
        assert result["matched_philosophy"] == "程序正义"

    def test_strips_markdown_code_block(self):
        analyzer = make_analyzer(_fake_llm(
            '```json\n{"core_claim": "c","underlying_assumption": "a","matched_philosophy": "未知"}\n```'
        ))
        result = analyzer(_base_state(user_input="test"))

        assert result["core_claim"] == "c"
        assert result["underlying_assumption"] == "a"
        assert result["matched_philosophy"] == "未知"

    def test_strips_markdown_without_language_label(self):
        analyzer = make_analyzer(_fake_llm(
            '```\n{"core_claim": "x","underlying_assumption": "y","matched_philosophy": "功利主义"}\n```'
        ))
        result = analyzer(_base_state())

        assert result["core_claim"] == "x"
        assert result["matched_philosophy"] == "功利主义"

    def test_json_decode_error_falls_back_to_raw(self):
        analyzer = make_analyzer(_fake_llm("not valid json at all"))
        result = analyzer(_base_state(user_input="hello"))

        assert result["core_claim"].startswith("[RAW]")
        assert result["matched_philosophy"] == "未知"

    def test_missing_fields_get_defaults(self):
        analyzer = make_analyzer(_fake_llm('{"core_claim": "only claim"}'))
        result = analyzer(_base_state())

        assert result["core_claim"] == "only claim"
        assert result["underlying_assumption"] == ""
        assert result["matched_philosophy"] == "未知"


# ---------- Socratic Ironist ----------

class TestSocraticIronist:
    """Socratic_Ironist 节点的基本行为测试。"""

    def test_passes_state_fields_to_llm(self):
        ironist = make_socratic_ironist(_fake_llm("你确定你的前提是对的吗？"))
        state = _base_state(
            core_claim="努力=成功",
            underlying_assumption="机会均等",
            rag_counter_example="起点不平等",
        )
        result = ironist(state)

        assert result["socratic_question"] == "你确定你的前提是对的吗？"

    def test_output_is_non_empty(self):
        ironist = make_socratic_ironist(_fake_llm("反问句"))
        state = _base_state(
            core_claim="CC",
            underlying_assumption="UA",
            rag_counter_example="RAG",
        )
        result = ironist(state)

        assert len(result["socratic_question"]) > 0
