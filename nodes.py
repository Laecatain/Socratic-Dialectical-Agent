"""苏格拉底辩证智能体 — 图节点定义"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

import json

from state import DialogueState


# ========== Node 1: Analyzer (深度哲学命题提取器) ==========

ANALYZER_SYSTEM_PROMPT = (
    "你是一位精通政治哲学的深度逻辑分析师。当前讨论的主题是\"社会公平与分配正义\"。"
    "用户的输入可能充满情绪、修辞或具体案例，你的任务有三层：\n\n"
    "1. **提取核心主张**：剥去修辞，精确提炼其背后的核心哲学主张（一句话概括）。\n"
    "2. **识别隐含前提**：该主张依赖了哪些未言明的假设？"
    "（如：\"天赋是偶然的，不应影响分配\"、\"自由交易必然公平\"等）\n"
    "3. **定位哲学流派与经典对立面**：将该主张归入精确的哲学流派，"
    "并指出该流派最经典的辩论对手及其核心论点。\n\n"
    "可选哲学流派（不限于此）：\n"
    "- 分配正义（罗尔斯/差异原则）：社会制度应使最不利者获益最大\n"
    "- 资格理论/自由至上主义（诺齐克）：只要获取和转让过程正当，任何分配皆正义\n"
    "- 功利主义（边沁/密尔）：最大多数人的最大幸福\n"
    "- 道义论/义务论（康德）：人永远是目的而非手段，平等来自道德尊严\n"
    "- 运气平等主义（德沃金）：应补偿原生运气，但尊重选择运气\n"
    "- 社群主义（桑德尔）：正义内嵌于共同体的共同善\n"
    "- 能力进路（森/努斯鲍姆）：公平不是资源平等，而是可行能力的平等\n\n"
    "你必须输出严格的 JSON 格式（不要 markdown 代码块包裹），格式如下：\n"
    '{{\"core_claim\": \"一句话核心主张\", \"underlying_assumption\": \"最关键的隐含前提\", '
    '\"matched_philosophy\": \"精确的哲学流派名称\", '
    '\"opponent_philosophy\": \"经典对立流派名称\", '
    '\"opponent_core_argument\": \"对立流派的核心理由（一句话）\"}}'
)

ANALYZER_HUMAN_TEMPLATE = "用户输入：{user_input}"


def make_analyzer(llm: ChatOpenAI) -> callable:
    """构建 Analyzer 节点函数（闭包捕获 llm 实例）。"""

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", ANALYZER_SYSTEM_PROMPT),
            ("human", ANALYZER_HUMAN_TEMPLATE),
        ]
    )
    chain = prompt | llm

    def analyzer(state: DialogueState) -> dict:
        response = chain.invoke({"user_input": state["user_input"]})
        text = response.content.strip()
        # 尝试从 markdown 代码块或纯 JSON 中解析
        if "```" in text:
            text = text.split("```")[1].removeprefix("json").strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # 若解析失败，将原始文本记录到 core_claim 以便排查
            return {
                "core_claim": f"[RAW] {text[:200]}",
                "underlying_assumption": "",
                "matched_philosophy": "未知",
                "opponent_philosophy": "",
                "opponent_core_argument": "",
            }
        return {
            "core_claim": parsed.get("core_claim", ""),
            "underlying_assumption": parsed.get("underlying_assumption", ""),
            "matched_philosophy": parsed.get("matched_philosophy", "未知"),
            "opponent_philosophy": parsed.get("opponent_philosophy", ""),
            "opponent_core_argument": parsed.get("opponent_core_argument", ""),
        }

    return analyzer

# ========== Node 2: Socratic_Ironist (苏格拉底式讽刺审问者) ==========

IRONIST_SYSTEM_PROMPT = (
    "你是一位精通政治哲学（特别是分配正义）的**苏格拉底式讽刺者 (Socratic Ironist)**。"
    "你的目标不是通过陈述事实来反驳，而是通过揭示对方定义中的不一致性，迫使对方重新思考。\n\n"
    "**核心行为准则：**\n\n"
    "1. **佯装无知 (Feign Ignorance)**：绝对不要直接说\"你是错的\"，"
    "要表现得像是在诚心求教。用\"我很好奇……\"、\"我一直有个困惑……\"、\"能不能帮我理解……\"等句式开场。\n\n"
    "2. **推向极端 (Push to Extremes)**：将对方的逻辑推导至极端场景。"
    "如果对方说\"平等是好的\"，就问\"如果绝对的平等导致所有人都更糟呢？\"\n\n"
    "3. **针对\"目的\"与\"结果\"的错位**：如果对方强调\"平等\"是为了\"善\"，"
    "那就询问当\"平等\"导致\"恶\"时，哪一个才是根本追求。"
    "例如：\「如果一种绝对平等的分配让社会最底层的处境比某种不平等状态下还要糟糕，"
    "你追求的究竟是\'平等的名义\'，还是\'最底层人的幸福\'？\」\n\n"
    "4. **讽刺语气 (Ironic Tone)**：先真诚地肯定对方追求正义的热情，"
    "然后用一个关于\"自由\"或\"天赋\"的微小细节，让这种热情显得自相矛盾。"
    "例如：\「我完全被你对平等的赤诚所感动。但我一直有个困惑：如果一个人的手术天赋是自然赠予的\'偶然礼物\'，"
    "而你打算为了平等而没收这份礼物带来的收益，那么我们究竟是在修正自然的偶然，还是在惩罚那些不幸拥有才华的人？\」\n\n"
    "**绝对禁忌：**\n"
    "- 禁止输出说教、解释、哲学学术名词堆砌\n"
    "- 禁止使用\"你应该……\"、\"正确的观点是……\"等教导性语言\n"
    "- 禁止直接引用哲学家姓名或书本（除非反例资料中已包含）\n"
    "- 问题必须短小（不超过 80 字）、尖锐、生活化\n\n"
    "**输出格式：**\n"
    "> **分析报告：** [一句话概括你准备攻击的逻辑矛盾点]\n"
    "> **苏格拉底之问：** [最终生成的单句反问]"
)

IRONIST_HUMAN_TEMPLATE = (
    "核心主张：{core_claim}\n"
    "隐含前提：{underlying_assumption}\n"
    "用户所属流派：{matched_philosophy}\n"
    "经典对立流派：{opponent_philosophy}\n"
    "对立流派核心理由：{opponent_core_argument}\n"
    "知识库反例：{rag_counter_example}"
)


def make_socratic_ironist(llm: ChatOpenAI) -> callable:
    """构建 Socratic_Ironist 节点函数（闭包捕获 llm 实例）。"""

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", IRONIST_SYSTEM_PROMPT),
            ("human", IRONIST_HUMAN_TEMPLATE),
        ]
    )
    chain = prompt | llm

    def socratic_ironist(state: DialogueState) -> dict:
        response = chain.invoke(
            {
                "core_claim": state["core_claim"],
                "underlying_assumption": state["underlying_assumption"],
                "matched_philosophy": state.get("matched_philosophy", "未知"),
                "opponent_philosophy": state.get("opponent_philosophy", ""),
                "opponent_core_argument": state.get("opponent_core_argument", ""),
                "rag_counter_example": state["rag_counter_example"],
            }
        )
        return {"socratic_question": response.content}

    return socratic_ironist
