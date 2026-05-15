"""动态知识流 — Tavily Web Search 节点

当 ChromaDB 检索相似度不足时，通过 Tavily API 搜索互联网反例，
将网页摘要注入 rag_counter_example 供 Socratic_Ironist 使用。
"""

import os

from state import DialogueState

# ---------- 配置 ----------
MAX_RESULTS = 3

WEB_SEARCH_QUERY_SUFFIX = " 反驳 批评 哲学反例 对立观点"


def make_web_search() -> callable:
    """构建 Web_Search 节点函数。

    需要环境变量 TAVILY_API_KEY。
    若 API Key 未配置或调用失败，自动降级为 fallback 模式。
    """

    def web_search(state: DialogueState) -> dict:
        core_claim = state.get("core_claim", "")
        if not core_claim:
            return {
                "rag_counter_example": "[FALLBACK] 未提取到核心主张，无法进行网络搜索。",
                "knowledge_source": "fallback",
            }

        api_key = os.getenv("TAVILY_API_KEY", "").strip()
        if not api_key:
            print("[WEB_SEARCH] TAVILY_API_KEY 未配置，跳过网络搜索。")
            return {
                "rag_counter_example": (
                    state.get("rag_counter_example", "")
                    + "\n\n[FALLBACK] 网络搜索 API Key 未配置。"
                ),
                "knowledge_source": "fallback",
            }

        search_query = f"{core_claim}{WEB_SEARCH_QUERY_SUFFIX}"
        print(f"[WEB_SEARCH] 搜索查询: {search_query[:120]}")

        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=api_key)
            response = client.search(
                query=search_query,
                search_depth="basic",
                max_results=MAX_RESULTS,
            )

            results = response.get("results", [])
            if not results:
                return {
                    "rag_counter_example": (
                        state.get("rag_counter_example", "")
                        + "\n\n[FALLBACK] 网络搜索未返回有效结果。"
                    ),
                    "knowledge_source": "fallback",
                }

            snippets: list[str] = []
            for i, result in enumerate(results[:MAX_RESULTS], 1):
                title = result.get("title", "未知来源")
                snippet = result.get("content", "")
                url = result.get("url", "")
                snippets.append(
                    f"[网络搜索 #{i}] {title}\n{snippet}\n来源: {url}"
                )

            web_result = "\n\n---\n\n".join(snippets)

            # 与 ChromaDB 已有结果合并
            existing = state.get("rag_counter_example", "")
            if existing and not existing.startswith("[RETRIEVER]"):
                merged = existing + "\n\n=== 网络搜索结果 ===\n\n" + web_result
            else:
                merged = web_result

            print(f"[WEB_SEARCH] 成功获取 {len(snippets)} 条网络结果")

            return {
                "rag_counter_example": merged,
                "knowledge_source": "web_search",
            }

        except ImportError:
            print("[WEB_SEARCH] tavily-python 未安装，请执行: pip install tavily-python")
            return {
                "rag_counter_example": (
                    state.get("rag_counter_example", "")
                    + "\n\n[FALLBACK] tavily-python 未安装。"
                ),
                "knowledge_source": "fallback",
            }
        except Exception as e:
            print(f"[WEB_SEARCH] 网络搜索失败: {e}")
            return {
                "rag_counter_example": (
                    state.get("rag_counter_example", "")
                    + "\n\n[FALLBACK] 网络搜索暂时不可用，请基于常识进行追问。"
                ),
                "knowledge_source": "fallback",
            }

    return web_search
