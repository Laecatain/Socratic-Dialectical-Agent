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
    '你是一个批判性思维分析器。当前讨论的主题是"社会公平"。'
    '用户表达了一个核心主张，你的任务不是赞同它，'
    '而是构造一个"反事实查询词"——即在向量数据库中搜索"能反驳该主张的反例"时，'
    '最可能命中相关文档的搜索短语。\n\n'
    '规则：\n'
    '1. 输出必须是纯文本短句（不超过 50 字），不要有任何前缀或解释。\n'
    '2. 反事实查询词应当包含该主张的"反面"关键词，'
    '例如攻击该主张的后果、挑战其前提、或描述一种反例场景。\n'
    '3. 你不需要输出完整的反例本身，只需要生成一个"适合用于语义搜索的查询短语"。\n\n'
    '示例：\n'
    '- 用户观点："富人应该多交税" → "向富人征税的不良后果或侵犯产权的反例"\n'
    '- 用户观点："教育机会应该完全平等" → "教育资源倾斜分配的反例 精英筛选的必要性"\n'
    '- 用户观点："社会福利越多越好" → "福利依赖导致个人努力下降的反面案例"'
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
                    f"[FATAL] 无法连接 ChromaDB（路径: {CHROMA_PERSIST_DIR}）: {e}\n"
                    f"请先运行 ingest.py 构建向量库。"
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
            print(f"[WARN] 反事实查询词生成失败 ({e})，降级为直接检索。")

        print(f"[INFO] 用户主张: {core_claim}")
        print(f"[INFO] 反事实查询词: {counter_query}")

        # ---- Step 2: 在 ChromaDB 中检索反例 ----
        store = _get_vector_store()
        try:
            results = store.similarity_search(
                query=counter_query,
                k=TOP_K,
                filter={"type": "counter_example"},  # 关键：只返回反例类型
            )
        except Exception as e:
            return {
                "rag_counter_example": (
                    f"[RETRIEVER] ChromaDB 检索失败: {e}"
                )
            }

        # ---- Step 3: 拼接结果 ----
        if not results:
            return {
                "rag_counter_example": (
                    "[RETRIEVER] 未检索到匹配的反例文档。"
                )
            }

        retrieved_texts: list[str] = []
        for i, doc in enumerate(results, 1):
            philosophy = doc.metadata.get("philosophy", "未知")
            author = doc.metadata.get("author", "未知")
            retrieved_texts.append(
                f"[反例 #{i}] 流派: {philosophy} | 来源: {author}\n{doc.page_content}"
            )

        rag_result = "\n\n---\n\n".join(retrieved_texts)
        print(f"[INFO] 检索到 {len(results)} 条反例。")

        return {"rag_counter_example": rag_result}

    return retrieve_contradiction