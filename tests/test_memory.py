"""测试多轮对话记忆与逻辑矛盾检测（test_memory.py）

覆盖：
- AdmittedPremise Pydantic 模型
- AnalyzerMultiTurnOutput 模型
- Analyzer 跨轮次矛盾检测
- Socratic_Ironist 伏击模式
- 3 轮端到端逻辑伏击模拟
"""

import json

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from nodes import make_analyzer, make_socratic_ironist
from state import AdmittedPremise, AnalyzerMultiTurnOutput


# ---------- helpers ----------

def _fake_llm(text: str):
    """构造一个返回指定 AIMessage 的 LangChain Runnable。"""
    def _invoke(messages, **kwargs):
        return AIMessage(content=text)
    return RunnableLambda(_invoke)


def _fake_llm_dynamic(response_fn):
    """构造一个根据输入动态返回内容的 Runnable。

    response_fn(messages, kwargs) -> str
    """
    def _invoke(messages, **kwargs):
        content = response_fn(messages, kwargs)
        return AIMessage(content=content)
    return RunnableLambda(_invoke)


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
        "admitted_premises": [],
        "has_contradiction": False,
        "contradiction_details": None,
        "target_premise_id": None,
        "target_premise_statement": None,
        "target_premise_turn": None,
    }
    s.update(overrides)
    return s


# ---------- AdmittedPremise 模型 ----------

class TestAdmittedPremise:
    """AdmittedPremise Pydantic 模型测试。"""

    def test_valid_premise(self):
        p = AdmittedPremise(
            premise_id="PREMISE_001",
            turn_index=1,
            statement="自由高于一切",
            philosophical_alignment="资格理论",
        )
        assert p.premise_id == "PREMISE_001"
        assert p.turn_index == 1
        assert p.statement == "自由高于一切"
        assert p.is_active is True

    def test_premise_serialization(self):
        p = AdmittedPremise(
            premise_id="PREMISE_002",
            turn_index=2,
            statement="平等是最高价值",
            philosophical_alignment="分配正义",
            is_active=True,
        )
        d = p.model_dump()
        assert d["premise_id"] == "PREMISE_002"
        assert d["statement"] == "平等是最高价值"
        assert d["is_active"] is True

    def test_inactive_premise(self):
        p = AdmittedPremise(
            premise_id="PREMISE_003",
            turn_index=1,
            statement="被推翻的前提",
            philosophical_alignment="未知",
            is_active=False,
        )
        assert p.is_active is False


# ---------- AnalyzerMultiTurnOutput 模型 ----------

class TestAnalyzerMultiTurnOutput:
    """AnalyzerMultiTurnOutput 多轮审计模型测试。"""

    def test_no_contradiction_output(self):
        output = AnalyzerMultiTurnOutput(
            core_claim="公平很重要",
            underlying_assumption="社会应该平等",
            matched_philosophy="分配正义",
            opponent_philosophy="资格理论",
            opponent_core_argument="自由优先于平等",
        )
        assert output.detected_contradiction is False
        assert output.contradiction_analysis is None
        assert output.conflicting_premise_id is None
        assert output.extracted_new_premise is None

    def test_with_contradiction(self):
        output = AnalyzerMultiTurnOutput(
            core_claim="为了秩序必须限制自由",
            underlying_assumption="集体安全高于个人权利",
            matched_philosophy="功利主义",
            opponent_philosophy="资格理论",
            opponent_core_argument="个人权利不可侵犯",
            extracted_new_premise="集体安全高于个人自由",
            detected_contradiction=True,
            contradiction_analysis="用户曾承认自由不可侵犯，现在却说为了秩序必须限制自由",
            conflicting_premise_id="PREMISE_001",
        )
        assert output.detected_contradiction is True
        assert output.conflicting_premise_id == "PREMISE_001"
        assert "自由不可侵犯" in output.contradiction_analysis

    def test_serializes_to_dict(self):
        output = AnalyzerMultiTurnOutput(
            core_claim="c",
            underlying_assumption="a",
            matched_philosophy="未知",
            detected_contradiction=True,
            contradiction_analysis="矛盾分析",
            conflicting_premise_id="PREMISE_001",
        )
        d = output.model_dump()
        assert d["core_claim"] == "c"
        assert d["detected_contradiction"] is True
        assert d["conflicting_premise_id"] == "PREMISE_001"


# ---------- Analyzer 多轮矛盾检测 ----------

NO_CONTRADICTION_JSON = json.dumps({
    "core_claim": "个人自由神圣不可侵犯",
    "underlying_assumption": "自由是最高政治价值",
    "matched_philosophy": "资格理论",
    "opponent_philosophy": "分配正义",
    "opponent_core_argument": "公平有时需要限制自由",
    "extracted_new_premise": "个人自由绝对优先于集体利益",
    "detected_contradiction": False,
    "contradiction_analysis": None,
    "conflicting_premise_id": None,
})

CONTRADICTION_JSON = json.dumps({
    "core_claim": "国家必须强制隔离感染者",
    "underlying_assumption": "公共危机时集体安全高于个人自由",
    "matched_philosophy": "功利主义",
    "opponent_philosophy": "资格理论",
    "opponent_core_argument": "强制侵犯个人权利",
    "extracted_new_premise": "公共危机时国家强制力具有优先性",
    "detected_contradiction": True,
    "contradiction_analysis": "用户曾在第1轮承认个人自由绝对优先于集体利益，但本轮声称公共危机时集体安全高于个人自由。这是对'自由不可侵犯'原则的自我否定。",
    "conflicting_premise_id": "PREMISE_001",
})


class TestAnalyzerMultiTurn:
    """Analyzer 节点的跨轮次矛盾检测测试。"""

    def test_first_turn_no_contradiction(self):
        """第一轮无历史前提，不应检测到矛盾。"""
        analyzer = make_analyzer(_fake_llm(NO_CONTRADICTION_JSON))
        result = analyzer(_base_state(
            user_input="个人自由神圣不可侵犯，国家无权干涉",
            turn_count=1,
        ))

        assert result["core_claim"] == "个人自由神圣不可侵犯"
        assert result["has_contradiction"] is False
        # 应提取新前提并加入 admitted_premises
        assert len(result["admitted_premises"]) == 1
        assert result["admitted_premises"][0]["premise_id"] == "PREMISE_001"
        assert "自由" in result["admitted_premises"][0]["statement"]

    def test_second_turn_with_contradiction(self):
        """第二轮输入与历史前提矛盾，应检测到。"""
        analyzer = make_analyzer(_fake_llm(CONTRADICTION_JSON))
        result = analyzer(_base_state(
            user_input="国家必须强行隔离所有感染者",
            turn_count=2,
            admitted_premises=[{
                "premise_id": "PREMISE_001",
                "turn_index": 1,
                "statement": "个人自由绝对优先于集体利益",
                "philosophical_alignment": "资格理论",
                "is_active": True,
            }],
        ))

        assert result["has_contradiction"] is True
        assert result["target_premise_id"] == "PREMISE_001"
        assert result["target_premise_statement"] == "个人自由绝对优先于集体利益"
        assert result["target_premise_turn"] == 1
        assert "自由" in (result["contradiction_details"] or "")

    def test_no_contradiction_with_consistent_input(self):
        """前后一致的输入不应误报矛盾。"""
        analyzer = make_analyzer(_fake_llm(NO_CONTRADICTION_JSON))
        result = analyzer(_base_state(
            user_input="自由市场是最好的分配方式",
            turn_count=2,
            admitted_premises=[{
                "premise_id": "PREMISE_001",
                "turn_index": 1,
                "statement": "自由交易必然公平",
                "philosophical_alignment": "资格理论",
                "is_active": True,
            }],
        ))

        assert result["has_contradiction"] is False

    def test_duplicate_premise_not_added(self):
        """相同的前提不应重复加入 admitted_premises。"""
        analyzer = make_analyzer(_fake_llm(json.dumps({
            "core_claim": "x",
            "underlying_assumption": "y",
            "matched_philosophy": "资格理论",
            "opponent_philosophy": "",
            "opponent_core_argument": "",
            "extracted_new_premise": "个人自由绝对优先于集体利益",
            "detected_contradiction": False,
            "contradiction_analysis": None,
            "conflicting_premise_id": None,
        })))
        result = analyzer(_base_state(
            turn_count=2,
            admitted_premises=[{
                "premise_id": "PREMISE_001",
                "turn_index": 1,
                "statement": "个人自由绝对优先于集体利益",
                "philosophical_alignment": "资格理论",
                "is_active": True,
            }],
        ))

        # 不应添加重复的前提
        assert len(result["admitted_premises"]) == 1

    def test_empty_history_passed_as_null(self):
        """空历史前提时传入占位文本。"""
        # 验证 prompt 包含 "空" 标识 — 通过检查输出
        analyzer = make_analyzer(_fake_llm(NO_CONTRADICTION_JSON))
        result = analyzer(_base_state(turn_count=1))

        assert result["has_contradiction"] is False
        assert result["core_claim"] == "个人自由神圣不可侵犯"

    def test_markdown_json_stripping_with_contradiction(self):
        """含 markdown 代码块的矛盾输出应被正确解析。"""
        analyzer = make_analyzer(_fake_llm(
            '```json\n' + CONTRADICTION_JSON + '\n```'
        ))
        result = analyzer(_base_state(
            user_input="test",
            turn_count=2,
            admitted_premises=[{
                "premise_id": "PREMISE_001",
                "turn_index": 1,
                "statement": "个人自由绝对优先于集体利益",
                "philosophical_alignment": "资格理论",
                "is_active": True,
            }],
        ))

        assert result["has_contradiction"] is True
        assert result["target_premise_id"] == "PREMISE_001"


# ---------- Socratic_Ironist 伏击模式 ----------

AMBUSH_RESPONSE = (
    "> **分析报告：** 用户从'自由不可侵犯'滑向了'为了安全可以剥夺自由'\n"
    "> **苏格拉底之问：** 我很好奇，既然你之前说个人的自由连国家都无权剥夺，"
    "那这位不戴口罩的公民的自由，是在病毒面前突然贬值了吗？"
)

NORMAL_RESPONSE = (
    "> **分析报告：** 机会均等不等于起点均等\n"
    "> **苏格拉底之问：** 我很好奇，如果两个人站在不同的起跑线上，"
    "你让他们同时起跑，这算是公平吗？"
)


class TestIronistAmbush:
    """Socratic_Ironist 伏击模式测试。"""

    def test_normal_mode_no_contradiction(self):
        """无矛盾时使用正常反问模板。"""
        ironist = make_socratic_ironist(_fake_llm(NORMAL_RESPONSE))
        result = ironist(_base_state(
            core_claim="努力就能成功",
            underlying_assumption="机会均等",
            rag_counter_example="起点不平等案例",
            has_contradiction=False,
        ))

        assert "机会均等" in result["socratic_question"]
        assert "苏格拉底之问" in result["socratic_question"]

    def test_ambush_mode_with_contradiction(self):
        """检测到矛盾时使用伏击模板。"""
        ironist = make_socratic_ironist(_fake_llm(AMBUSH_RESPONSE))
        result = ironist(_base_state(
            user_input="国家必须强制隔离所有感染者",
            core_claim="为了安全可以限制自由",
            underlying_assumption="集体安全高于一切",
            rag_counter_example="",
            has_contradiction=True,
            contradiction_details="用户曾承认自由不可侵犯，现在为安全放弃自由",
            target_premise_id="PREMISE_001",
            target_premise_statement="个人自由绝对优先于集体利益",
            target_premise_turn=1,
        ))

        assert "苏格拉底之问" in result["socratic_question"]
        assert "自由" in result["socratic_question"]

    def test_ambush_mentions_prior_premise(self):
        """伏击反问应勾连用户之前承认的前提。"""
        ironist = make_socratic_ironist(_fake_llm(AMBUSH_RESPONSE))
        result = ironist(_base_state(
            user_input="国家必须强制隔离所有感染者",
            core_claim="",
            underlying_assumption="",
            rag_counter_example="",
            has_contradiction=True,
            contradiction_details="矛盾",
            target_premise_statement="个人自由绝对优先于集体利益",
            target_premise_turn=1,
        ))

        # 伏击输出应包含对历史前提的回溯
        assert "不戴口罩" in result["socratic_question"] or "自由" in result["socratic_question"]


# ---------- 3 轮端到端逻辑伏击模拟 ----------

class TestThreeTurnAmbush:
    """模拟完整的 3 轮"引君入瓮"对话流程。"""

    def _make_turn_analyzer(self):
        """创建一个根据用户输入动态切换输出的 Analyzer。"""
        def response_fn(messages, kwargs):
            # 将 LangChain prompt 输出统一转为纯文本
            if hasattr(messages, "to_string"):
                prompt_text: str = messages.to_string()
            elif hasattr(messages, "to_messages"):
                prompt_text = " ".join(
                    getattr(m, "content", str(m))
                    for m in messages.to_messages()
                )
            elif isinstance(messages, list):
                prompt_text = " ".join(
                    getattr(m, "content", str(m)) if hasattr(m, "content") else str(m)
                    for m in messages
                )
            else:
                prompt_text = str(messages)

            has_history = "PREMISE_001" in prompt_text
            has_contradiction_signal = ("隔离" in prompt_text or "强制" in prompt_text)

            if has_history and has_contradiction_signal:
                return CONTRADICTION_JSON
            return NO_CONTRADICTION_JSON

        return make_analyzer(_fake_llm_dynamic(response_fn))

    def test_three_turn_contradiction_flow(self):
        """模拟 3 轮对话，验证第 3 轮触发逻辑伏击。

        流程：
        T1: 用户说"自由不可侵犯" → 提取 PREMISE_001，无矛盾
        T2: 用户说"自由市场最好" → 一致，无矛盾
        T3: 用户说"国家必须强制隔离" → 矛盾！触发伏击
        """
        analyzer = self._make_turn_analyzer()

        # === Turn 1: 建立前提 ===
        t1 = analyzer(_base_state(
            user_input="个人消极自由神圣不可侵犯",
            turn_count=1,
        ))
        assert t1["has_contradiction"] is False
        assert len(t1["admitted_premises"]) >= 1
        premises = t1["admitted_premises"]

        # === Turn 2: 一致观点，不触发矛盾 ===
        t2 = analyzer(_base_state(
            user_input="自由市场交易是最好的分配方式",
            turn_count=2,
            admitted_premises=premises,
        ))
        assert t2["has_contradiction"] is False
        premises_t2 = t2["admitted_premises"]

        # === Turn 3: 矛盾爆发 ===
        t3 = analyzer(_base_state(
            user_input="面对传染病，国家必须强制隔离所有感染者",
            turn_count=3,
            admitted_premises=premises_t2,
        ))
        assert t3["has_contradiction"] is True
        assert t3["target_premise_id"] is not None
        assert t3["contradiction_details"] is not None

    def test_ironist_ambush_with_full_context(self):
        """验证 Ironist 在完整上下文下生成伏击反问。"""
        ironist = make_socratic_ironist(_fake_llm(AMBUSH_RESPONSE))

        result = ironist(_base_state(
            user_input="面对传染病，国家必须强制隔离所有感染者",
            core_claim="公共危机时集体安全高于个人自由",
            underlying_assumption="安全优先于自由",
            matched_philosophy="功利主义",
            opponent_philosophy="资格理论",
            opponent_core_argument="个人权利不可侵犯",
            rag_counter_example="",
            rag_relevance_score=0.0,
            knowledge_source="fallback",
            has_contradiction=True,
            contradiction_details="用户曾承认自由不可侵犯，现在为安全放弃自由。明显的双重标准。",
            target_premise_id="PREMISE_001",
            target_premise_statement="个人自由绝对优先于集体利益",
            target_premise_turn=1,
        ))

        assert "苏格拉底之问" in result["socratic_question"]
        # 伏击应同时包含对历史前提和当前暴论的勾连
        text = result["socratic_question"]
        has_ambush_marker = (
            "自由" in text or
            "不戴口罩" in text or
            "贬值" in text
        )
        assert has_ambush_marker, f"伏击反问应勾连前提与暴论，实际输出: {text}"
