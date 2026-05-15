"""苏格拉底辩证智能体 — 核心数据结构"""

from typing import Literal, TypedDict

from pydantic import BaseModel, Field


# ---------- LangGraph 图状态 ----------

class DialogueState(TypedDict):
    """LangGraph StateGraph 的共享状态。"""

    user_input: str             # 用户当前的输入
    core_claim: str             # 提取出的核心主张
    underlying_assumption: str  # 命题的隐含前提
    matched_philosophy: str     # 匹配的哲学流派
    rag_counter_example: str    # RAG 检索到的反例/攻击点
    socratic_question: str      # 最终生成的苏格拉底式提问
    turn_count: int             # 对话轮数


# ---------- Analyzer 结构化输出模型 ----------

PhilosophyCategory = Literal[
    "分配正义",
    "程序正义",
    "功利主义",
    "未知",
]

class AnalyzerOutput(BaseModel):
    """Analyzer 节点强制输出的 JSON 结构。"""

    core_claim: str = Field(description="用户输入背后的核心主张")
    underlying_assumption: str = Field(description="该主张的隐含前提")
    matched_philosophy: PhilosophyCategory = Field(
        description="最匹配的哲学流派分类"
    )
