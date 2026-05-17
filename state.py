"""苏格拉底辩证智能体 — 核心数据结构"""

from typing import Literal, TypedDict, Optional

from pydantic import BaseModel, Field


# ---------- 结构化前提模型 ----------

class AdmittedPremise(BaseModel):
    """用户在辩论中已承认的哲学前提。"""

    premise_id: str = Field(description="格式如 PREMISE_001")
    turn_index: int = Field(description="用户承认该前提的对话轮次")
    statement: str = Field(description="用户当时表述的具体观点/被推导出的隐含前提")
    philosophical_alignment: str = Field(description="该前提对应的哲学流派或价值取向")
    is_active: bool = Field(default=True, description="该前提当前是否仍然有效（未被用户主动推翻）")


# ---------- LangGraph 图状态 ----------

class DialogueState(TypedDict):
    """LangGraph StateGraph 的共享状态。"""

    user_input: str             # 用户当前的输入
    core_claim: str             # 提取出的核心主张
    underlying_assumption: str  # 命题的隐含前提
    matched_philosophy: str     # 匹配的哲学流派
    opponent_philosophy: str    # 经典对立流派
    opponent_core_argument: str # 对立流派的核心理由
    rag_counter_example: str    # RAG 检索到的反例/攻击点
    rag_relevance_score: float  # ChromaDB 检索最佳余弦距离（越小越相似）
    knowledge_source: str       # 知识来源: chromadb / web_search / fallback
    socratic_question: str      # 最终生成的苏格拉底式提问
    turn_count: int             # 对话轮数

    # ====== 多轮持久化字段 ======
    admitted_premises: list[dict]       # 用户历次承认的前提库 (AdmittedPremise 序列化)
    has_contradiction: bool             # 本轮是否抓住用户前后矛盾
    contradiction_details: Optional[str]  # 矛盾点的深度解剖描述
    target_premise_id: Optional[str]    # 遭受伏击的历史前提 ID
    target_premise_statement: Optional[str]  # 被攻击前提的原文
    target_premise_turn: Optional[int]  # 被攻击前提的轮次


# ---------- Analyzer 结构化输出模型 ----------

PhilosophyCategory = Literal[
    "分配正义",
    "程序正义",
    "功利主义",
    "道义论",
    "资格理论",
    "运气平等主义",
    "社群主义",
    "能力进路",
    "未知",
]

class AnalyzerOutput(BaseModel):
    """Analyzer 节点强制输出的 JSON 结构。"""

    core_claim: str = Field(description="用户输入背后的核心主张")
    underlying_assumption: str = Field(description="该主张的隐含前提")
    matched_philosophy: PhilosophyCategory = Field(
        description="最匹配的哲学流派分类"
    )
    opponent_philosophy: str = Field(
        default="",
        description="经典对立流派名称"
    )
    opponent_core_argument: str = Field(
        default="",
        description="对立流派的核心理由"
    )


class AnalyzerMultiTurnOutput(BaseModel):
    """Analyzer 多轮审计输出模型 — 包含跨轮次矛盾检测。"""

    core_claim: str = Field(description="用户输入背后的核心主张")
    underlying_assumption: str = Field(description="该主张的隐含前提")
    matched_philosophy: PhilosophyCategory = Field(
        description="最匹配的哲学流派分类"
    )
    opponent_philosophy: str = Field(
        default="",
        description="经典对立流派名称"
    )
    opponent_core_argument: str = Field(
        default="",
        description="对立流派的核心理由"
    )

    # 多轮审计字段
    extracted_new_premise: Optional[str] = Field(
        default=None,
        description="从当前输入中提炼出的、可沉淀为后续靶子的哲学前提"
    )
    detected_contradiction: bool = Field(
        default=False,
        description="当前输入是否与已承认的历史前提存在逻辑冲突"
    )
    contradiction_analysis: Optional[str] = Field(
        default=None,
        description="若有冲突，深度解剖其前后逻辑的自我坍塌"
    )
    conflicting_premise_id: Optional[str] = Field(
        default=None,
        description="冲突对应的历史 PREMISE_001 ID"
    )
