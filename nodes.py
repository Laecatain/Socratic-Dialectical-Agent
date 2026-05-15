"""苏格拉底辩证智能体 — 图节点定义"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

import json

from state import DialogueState


# ========== Node 1: Analyzer (命题提取器) ==========

ANALYZER_SYSTEM_PROMPT = (
    "你是一个严格的逻辑分析师。当前讨论的主题是“社会公平”。"
    "用户的输入可能充满情绪或具体案例，你的任务是提取其背后的核心主张，"
    "并归类到特定的哲学阵营。请客观冷酷地剖析其隐含前提。"
    "\n\n你必须输出严格的 JSON 格式（不要 markdown 包裹），格式如下：\n"
    '{{"core_claim": "核心主张", "underlying_assumption": "隐含前提", '
    '"matched_philosophy": "分配正义|程序正义|功利主义|未知"}}'
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
            }
        return {
            "core_claim": parsed.get("core_claim", ""),
            "underlying_assumption": parsed.get("underlying_assumption", ""),
            "matched_philosophy": parsed.get("matched_philosophy", "未知"),
        }

    return analyzer


# ========== Node 2: Socratic_Ironist (苏格拉底质询者) ==========

IRONIST_SYSTEM_PROMPT = (
    "你现在是苏格拉底。你必须保持谦逊，"
    "绝对不要使用生僻的哲学词汇，也不要直接指出对方的错误。"
    "结合用户的核心主张和知识库提供的反例攻击点，"
    "向用户提出一个短小、尖锐且生活化的反问句。"
    "这个反问句必须迫使对方重新思考其隐含前提。"
    "绝对禁忌：只能输出一个问句，"
    "绝对不能有任何说教、解释、铺垫或肯定对方的话语。"
)

IRONIST_HUMAN_TEMPLATE = (
    "核心主张：{core_claim}\n"
    "隐含前提：{underlying_assumption}\n"
    "反例攻击点：{rag_counter_example}"
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
                "rag_counter_example": state["rag_counter_example"],
            }
        )
        return {"socratic_question": response.content}

    return socratic_ironist
