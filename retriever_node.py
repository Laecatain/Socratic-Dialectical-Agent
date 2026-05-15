"""Phase 3 — 对抗性检索器（Adversarial Retriever）

核心逻辑：
1. 从 state["core_claim"] 获取用户核心观点
2. 利用 LLM 生成"反事实查询词（Hypothetical Counter-Query）"
3. 拿着反事实查询词去 ChromaDB 检索，过滤 type=counter_example
4. 将 top_k=2 的结果拼接，更新到 state["rag_counter_example"]
"""

import os
import sys

from langchain_core.prompts import ChatPromptTemplate
from langchain_chroma import Chroma
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from state import DialogueState

# ---------- 从环境变量读取配置 ----------
CHROMA_PERSIST_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "chroma_db"
)
COLLECTION_NAME = "socratic_social_justice"
TOP_K = 2


# ---------- 反事实查询词生成 Prompt ----------

COUNTER_QUERY_SYSTEM_PROMPT = (
    '你是一个哲学批判性思维分析器。当前讨论的主题是"社会公平与分配正义"。'
    '用户表达了一个核心主张，并定位到了具体哲学流派。你的任务是构造一个'
    '\"反事实查询词\"——即在向量数据库中搜索\"经典辩论对立面的反例\"时，'
    '最可能命中相关文档的搜索短语。\n\n'
    '规则：\n'
    '1. 输出必须是纯文本短句（不超过 60 字），不要有任何前缀或解释。\n'
    '2. 反事实查询词应当优先包含经典哲学家的名字和核心理念的对立关键词。'
    '例如：\"罗尔斯的差异原则忽视了诺齐克的自我所有权\"、'
    '\"功利主义最大幸福原则对个体权利的践踏\"。\n'
    '3. 如果 Analyzer 已给出对立流派信息，请直接基于该对立流派构造查询。\n'
    '4. 你不需要输出完整的反例本身，只需要生成一个\"适合用于语义搜索的查询短语\"。\n\n'
    '经典对立关系参考：\n'
    '- 罗尔斯(分配正义/差异原则) ↔ 诺齐克(资格理论/自我所有权)\n'
    '- 功利主义(最大幸福) ↔ 道义论(个体权利不可侵犯)\n'
    '- 平等主义 ↔ 自由至上主义\n'
    '- 社群主义 ↔ 自由个人主义\n\n'
    '示例：\n'
    '- 用户流派=分配正义 → "诺齐克 资格理论 反例 自我所有权 再分配即强迫劳动"\n'
    '- 用户流派=功利主义 → "康德 道义论 反例 人永远是目的 功利计算侵犯个体尊严"\n'
    '- 用户观点：\"富人应该多交税\" → "诺齐克 征税等于强迫劳动 侵犯财产权 反例"\n'
    '- 用户观点：\"教育机会应该完全平等\" → "精英筛选必要性 自然天赋差异 反例 绝对平等的恶果"\n'
    '- 用户观点：\"社会福利越多越好\" → "福利依赖 人丧失独立性 德沃金 选择运气与原生运气"'
)

COUNTER_QUERY_HUMAN_TEMPLATE = '用户的核心主张：{core_claim}'


# ---------- 工厂函数 ----------

def make_retrieve_contradiction(
    llm: ChatOpenAI,
    embeddings: OpenAIEmbeddings,
) -> callable:
    """构建对抗性检索节点函数。

    Args:
        llm: 用于生成反事实查询词的 ChatOpenAI 实例。
        embeddings: 用于向量相似度检索的 OpenAIEmbeddings 实例。

    Returns:
        callable: 节点函数，接收 DialogueState 返回 dict。
    """
    # ---------- 初始化 LLM 链 ----------
    counter_query_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", COUNTER_QUERY_SYSTEM_PROMPT),
            ("human", COUNTER_QUERY_HUMAN_TEMPLATE),
        ]
    )
    counter_query_chain = counter_query_prompt | llm

    # ---------- 初始化 ChromaDB 连接 ----------
    vector_store: Chroma | None = None

    def _get_vector_store() -> Chroma:
        """懒加载 ChromaDB 连接。"""
        nonlocal vector_store
        if vector_store is None:
            try:
                vector_store = Chroma(
                    persist_directory=CHROMA_PERSIST_DIR,
                    embedding_function=embeddings,
                    collection_name=COLLECTION_NAME,
                )
            except Exception as e:
                sys.exit(
                    f"[FATAL] ChromaDB connection failed (path: {CHROMA_PERSIST_DIR}): {e}\n"
                    f"Please run ingest.py first to build the vector store."
                )
        return vector_store

    # ---------- 节点函数 ----------

    def retrieve_contradiction(state: DialogueState) -> dict:
        """对抗性检索：生成反事实查询 -> 检索反例 -> 拼接返回。

        与普通 RAG 不同：我们不拿着用户观点去找相似文本，
        而是用 LLM 生成"驳斥用户观点所需的反例查询词"，
        然后在 ChromaDB 中找到最匹配的反例。
        """
        core_claim = state.get("core_claim", "")
        if not core_claim:
            return {"rag_counter_example": "[RETRIEVER] 未能提取到核心主张，无法检索反例。"}

        # ---- Step 1: 生成反事实查询词 ----
        try:
            counter_query_response = counter_query_chain.invoke(
                {"core_claim": core_claim}
            )
            counter_query = counter_query_response.content.strip()
        except Exception as e:
            # 降级：直接用 core_claim 检索
            counter_query = core_claim
            print(f"[WARN] counter query generation failed ({e}), fallback to direct search")

        print(f"[INFO] user_claim: {core_claim[:80]}")
        print(f"[INFO] counter_query: {counter_query[:80]}")

        # ---- Step 2: 在 ChromaDB 中检索反例 ----
        store = _get_vector_store()
        try:
            results_with_scores = store.similarity_search_with_score(
                query=counter_query,
                k=TOP_K,
                filter={"type": "counter_example"},  # 关键：只返回反例类型
            )
        except Exception as e:
            return {
                "rag_counter_example": (
                    f"[RETRIEVER] ChromaDB 检索失败: {e}"
                ),
                "rag_relevance_score": 2.0,
                "knowledge_source": "fallback",
            }

        # ---- Step 3: 提取距离分数并拼接结果 ----
        if not results_with_scores:
            return {
                "rag_counter_example": (
                    "[RETRIEVER] 未检索到匹配的反例文档。"
                ),
                "rag_relevance_score": 2.0,
                "knowledge_source": "chromadb",
            }

        # 解包 Document + score (余弦距离, 越小越相似)
        best_score = min(score for _, score in results_with_scores)
        retrieved_texts: list[str] = []
        for i, (doc, score) in enumerate(results_with_scores, 1):
            philosophy = doc.metadata.get("philosophy", "未知")
            author = doc.metadata.get("author", "未知")
            retrieved_texts.append(
                f"[反例 #{i}] 流派: {philosophy} | 来源: {author} | 距离: {score:.4f}\n{doc.page_content}"
            )

        rag_result = "\n\n---\n\n".join(retrieved_texts)
        print(f"[INFO] retrieved {len(results_with_scores)} counter examples, best cosine distance: {best_score:.4f}")

        return {
            "rag_counter_example": rag_result,
            "rag_relevance_score": best_score,
            "knowledge_source": "chromadb",
        }

    return retrieve_contradiction