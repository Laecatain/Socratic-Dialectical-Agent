"""苏格拉底辩证智能体 — 图节点定义（多轮记忆版）"""

import json

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from state import DialogueState


# ========== Node 1: Analyzer (多轮哲学命题提取 + 矛盾检测) ==========

ANALYZER_SYSTEM_PROMPT = (
    "你是一位精通政治哲学的深度逻辑分析师与辩论裁判。当前讨论的主题是\"社会公平与分配正义\"。\n"
    "用户的输入可能充满情绪、修辞或具体案例，你的任务有四层：\n\n"
    "1. **提取核心主张**：剥去修辞，精确提炼其背后的核心哲学主张（一句话概括）。\n"
    "2. **识别隐含前提**：该主张依赖了哪些未言明的假设？"
    "（如：\"天赋是偶然的，不应影响分配\"、\"自由交易必然公平\"等）\n"
    "3. **定位哲学流派与经典对立面**：将该主张归入精确的哲学流派，"
    "并指出该流派最经典的辩论对手及其核心论点。\n"
    "4. **跨轮次逻辑审计**：对比用户当前输入与【历史已承认的前提列表】，"
    "检测是否存在自我矛盾、双重标准或定义滑坡。\n\n"
    "可选哲学流派（不限于此）：\n"
    "- 分配正义（罗尔斯/差异原则）：社会制度应使最不利者获益最大\n"
    "- 资格理论/自由至上主义（诺齐克）：只要获取和转让过程正当，任何分配皆正义\n"
    "- 功利主义（边沁/密尔）：最大多数人的最大幸福\n"
    "- 道义论/义务论（康德）：人永远是目的而非手段，平等来自道德尊严\n"
    "- 运气平等主义（德沃金）：应补偿原生运气，但尊重选择运气\n"
    "- 社群主义（桑德尔）：正义内嵌于共同体的共同善\n"
    "- 能力进路（森/努斯鲍姆）：公平不是资源平等，而是可行能力的平等\n\n"
    "【矛盾检测指南】：\n"
    "- 若用户曾在第N轮承认\"自由高于一切\"，本轮却说\"为了秩序必须限制自由\" → 显著矛盾\n"
    "- 若用户对本轮某个特殊案例使用了与之前不同的原则标准 → 双重标准\n"
    "- 若用户在讨论不同话题时偷偷改变了关键术语的定义 → 定义滑坡\n"
    "- 仅当存在实质性逻辑冲突时报告矛盾，不要牵强附会\n\n"
    "你必须输出严格的 JSON 格式（不要 markdown 代码块包裹），格式如下：\n"
    '{{"core_claim": "一句话核心主张", "underlying_assumption": "最关键的隐含前提", '
    '"matched_philosophy": "精确的哲学流派名称", '
    '"opponent_philosophy": "经典对立流派名称", '
    '"opponent_core_argument": "对立流派的核心理由（一句话）", '
    '"extracted_new_premise": "可从本轮提炼的哲学前提（若无可设为null）", '
    '"detected_contradiction": false, '
    '"contradiction_analysis": "若有矛盾，解剖其逻辑自我坍塌（若无可设为null）", '
    '"conflicting_premise_id": "冲突的历史前提ID，如PREMISE_001（若无可设为null）"}}'
)

ANALYZER_HUMAN_TEMPLATE = (
    "【历史已承认的前提列表】：\n"
    "{admitted_premises_json}\n\n"
    "【用户当前输入】：\n"
    "\"{user_input}\""
)


def make_analyzer(llm: ChatOpenAI) -> callable:
    """构建 Analyzer 节点函数（闭包捕获 llm 实例）。

    功能：
    1. 提炼当前轮次的核心主张、隐含前提、哲学流派
    2. 跨轮次比对历史 admitted_premises，检测逻辑矛盾
    3. 提取新前提供后续轮次追踪
    """

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", ANALYZER_SYSTEM_PROMPT),
            ("human", ANALYZER_HUMAN_TEMPLATE),
        ]
    )
    chain = prompt | llm

    def analyzer(state: DialogueState) -> dict:
        # 序列化历史前提为 JSON 供 LLM 审计
        admitted = state.get("admitted_premises", []) or []
        admitted_json = json.dumps(admitted, ensure_ascii=False, indent=2)
        if not admitted:
            admitted_json = "（空 — 这是第一轮对话，无历史前提可对比）"

        response = chain.invoke({
            "user_input": state["user_input"],
            "admitted_premises_json": admitted_json,
        })
        text = response.content.strip()

        # 尝试从 markdown 代码块或纯 JSON 中解析
        if "```" in text:
            text = text.split("```")[1].removeprefix("json").strip()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {
                "core_claim": f"[RAW] {text[:200]}",
                "underlying_assumption": "",
                "matched_philosophy": "未知",
                "opponent_philosophy": "",
                "opponent_core_argument": "",
                "has_contradiction": False,
            }

        # 提取矛盾检测结果
        has_contradiction = parsed.get("detected_contradiction", False)
        contradiction_analysis = parsed.get("contradiction_analysis")
        conflicting_premise_id = parsed.get("conflicting_premise_id")

        # 构建新的 admitted_premise（若提取到新前提）
        extracted_premise = parsed.get("extracted_new_premise")
        new_admitted = list(admitted)  # 不可变：复制新列表
        target_statement = None
        target_turn = None

        if extracted_premise:
            new_id = f"PREMISE_{len(new_admitted) + 1:03d}"
            turn = state.get("turn_count", 1)
            new_premise = {
                "premise_id": new_id,
                "turn_index": turn,
                "statement": extracted_premise,
                "philosophical_alignment": parsed.get("matched_philosophy", "未知"),
                "is_active": True,
            }
            # 避免重复添加相同的前提
            existing_statements = {p.get("statement", "") for p in new_admitted}
            if extracted_premise not in existing_statements:
                new_admitted.append(new_premise)

        # 若检测到矛盾，定位被攻击的历史前提详情
        if has_contradiction and conflicting_premise_id:
            for p in new_admitted:
                if p.get("premise_id") == conflicting_premise_id:
                    target_statement = p.get("statement", "")
                    target_turn = p.get("turn_index")
                    break

        return {
            "core_claim": parsed.get("core_claim", ""),
            "underlying_assumption": parsed.get("underlying_assumption", ""),
            "matched_philosophy": parsed.get("matched_philosophy", "未知"),
            "opponent_philosophy": parsed.get("opponent_philosophy", ""),
            "opponent_core_argument": parsed.get("opponent_core_argument", ""),
            "has_contradiction": has_contradiction,
            "contradiction_details": contradiction_analysis,
            "target_premise_id": conflicting_premise_id,
            "target_premise_statement": target_statement,
            "target_premise_turn": target_turn,
            "admitted_premises": new_admitted,
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
    "例如：「如果一种绝对平等的分配让社会最底层的处境比某种不平等状态下还要糟糕，"
    "你追求的究竟是'平等的名义'，还是'最底层人的幸福'？」\n\n"
    "4. **讽刺语气 (Ironic Tone)**：先真诚地肯定对方追求正义的热情，"
    "然后用一个关于\"自由\"或\"天赋\"的微小细节，让这种热情显得自相矛盾。"
    "例如：「我完全被你对平等的赤诚所感动。但我一直有个困惑：如果一个人的手术天赋是自然赠予的'偶然礼物'，"
    "而你打算为了平等而没收这份礼物带来的收益，那么我们究竟是在修正自然的偶然，还是在惩罚那些不幸拥有才华的人？」\n\n"
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
    "知识来源：{knowledge_source}\n"
    "知识相似度：{rag_relevance_score}\n"
    "  (提示：分数低于0.5则外部反例关联弱，加大自主发散)\n"
    "外部精准反例：{rag_counter_example}\n"
    "你必须借鉴的对立论证：{opponent_core_argument}\n"
    "审问指令：\n"
    "1. 观察用户暴论与隐含前提。\n"
    "2. 若外部反例有精妙思想实验，转化为尖锐生活反问。\n"
    "3. 严禁陈述句答案！佯装无知，用反问将逻辑推向荒谬极端。"
)

# ---------- 伏击模式提示词 ----------

IRONIST_AMBUSH_SYSTEM = (
    "你现在是苏格拉底本人。在辩论中，用户已经掉入了你布下的逻辑陷阱。"
    "他刚刚说的话，与他之前亲自承认的原则发生了严重的自我坍塌！\n\n"
    "**你的武器：**\n"
    "1. 摆出你经典的\"假装无知\"姿态，但言辞要如手术刀般精准。\n"
    "2. 你**必须**在一句生活化的反问中，同时勾连出他【此前承认的原则】与【当下的暴论】，"
    "逼迫他直面自己的双重标准。\n"
    "3. 严禁给出长篇大论的客套说教！只用一记灵魂反问完成致命一击。\n"
    "4. 用\"我很好奇……\"、\"能不能帮我理解……\"等句式开场，但内核是冷酷的逻辑处刑。\n\n"
    "**输出格式：**\n"
    "> **分析报告：** [一句话概括逻辑坍塌点]\n"
    "> **苏格拉底之问：** [单句反问，同时勾连历史前提与当前暴论]"
)

IRONIST_AMBUSH_HUMAN = (
    "【用户此前承认的原则】：{target_premise_statement}"
    "（发表于第 {target_premise_turn} 轮）\n"
    "【用户当下展现的暴论】：{current_user_input}\n"
    "【矛盾解剖】：{contradiction_details}\n"
    "【审问执行指令】：\n"
    "你必须在一句反问中同时勾连他【此前承认的原则】与【当下的暴论】，"
    "逼迫他直面自己的双重标准。用\"我很好奇……\"开场。"
)


def make_socratic_ironist(llm: ChatOpenAI) -> callable:
    """构建 Socratic_Ironist 节点函数（闭包捕获 llm 实例）。

    支持两种模式：
    - 正常模式：基于外部反例和哲学对立进行苏格拉底式反问
    - 伏击模式：当 has_contradiction=True 时，用用户自己的历史言论进行逻辑处刑
    """

    normal_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", IRONIST_SYSTEM_PROMPT),
            ("human", IRONIST_HUMAN_TEMPLATE),
        ]
    )
    normal_chain = normal_prompt | llm

    ambush_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", IRONIST_AMBUSH_SYSTEM),
            ("human", IRONIST_AMBUSH_HUMAN),
        ]
    )
    ambush_chain = ambush_prompt | llm

    def socratic_ironist(state: DialogueState) -> dict:
        has_contradiction = state.get("has_contradiction", False)

        if has_contradiction:
            # 伏击模式：用用户自己的历史言论进行逻辑围剿
            target_statement = state.get("target_premise_statement", "")
            target_turn = state.get("target_premise_turn", "?")
            contradiction_details = state.get("contradiction_details", "")
            user_input = state.get("user_input", "")

            response = ambush_chain.invoke({
                "target_premise_statement": target_statement,
                "target_premise_turn": target_turn,
                "current_user_input": user_input,
                "contradiction_details": contradiction_details,
            })
            return {"socratic_question": response.content}

        # 正常模式：基于外部反例和对立论证
        response = normal_chain.invoke({
            "core_claim": state["core_claim"],
            "underlying_assumption": state["underlying_assumption"],
            "matched_philosophy": state.get("matched_philosophy", "未知"),
            "opponent_philosophy": state.get("opponent_philosophy", ""),
            "opponent_core_argument": state.get("opponent_core_argument", ""),
            "rag_counter_example": state["rag_counter_example"],
            "rag_relevance_score": state.get("rag_relevance_score", 0.0),
            "knowledge_source": state.get("knowledge_source", "unknown"),
        })
        return {"socratic_question": response.content}

    return socratic_ironist
