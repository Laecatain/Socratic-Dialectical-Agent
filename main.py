        "rag_counter_example": "",
        "rag_relevance_score": 0.0,
        "knowledge_source": "",
        "socratic_question": "",
        "turn_count":chain_openai import ChatOpenAI, OpenAIEmbeddings

from graph import build_graph


def _init_llm_and_graph() -> tuple[ChatOpenAI, OpenAIEmbeddings, callable]:
    """初始化 LLM、Embeddings 并构建编译好的 LangGraph 应用。

    Embedding 配置优先使用 EMBEDDING_* 环境变量，回退到 OPENAI_*。
    """
    api_key = os.getenv("OPENAI_API_KEY")
    api_base = os.getenv("OPENAI_API_BASE")
    model_name = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")

    # Embedding 独立配置（支持不同的 API 网关）
    embed_api_key = os.getenv("EMBEDDING_API_KEY") or api_key
    embed_api_base = os.getenv("EMBEDDING_API_BASE") or api_base
    embed_model = os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-3-small")

    if not api_key:
        sys.exit("错误: 未设置 OPENAI_API_KEY。请在 .env 文件中配置。")

    # 初始化 Chat LLM
    llm = ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=api_base,
        temperature=0.7,
    )

    # 初始化 Embeddings（用于 ChromaDB 检索）
    embed_kwargs: dict = {
        "model": embed_model,
        "api_key": embed_api_key,
    }
    # 对于非 OpenAI 兼容网关（如 DashScope），需要禁用 token 拆分
    embed_kwargs["check_embedding_ctx_length"] = False
    if embed_api_base:
        base = embed_api_base.rstrip("/")
        if not base.endswith("/v1"):
            base += "/v1"
        embed_kwargs["base_url"] = base
    embeddings = OpenAIEmbeddings(**embed_kwargs)

    app = build_graph(llm, embeddings)
    return llm, embeddings, app


def _run_once(user_input: str) -> None:
    """单次执行模式：接受一个观点，输出苏格拉底的提问后退出。"""
    _, _, app = _init_llm_and_graph()
    result = app.invoke({
        "user_input": user_input,
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
    })
    question = result.get("socratic_question", "(未生成提问)")
    print(f"你: {user_input}")
    print(f"\n苏格拉底: {question}\n")
    if os.getenv("DEBUG", "").lower() in ("1", "true", "yes"):
        print(f"  [DEBUG] 核心主张: {result.get('core_claim')}")
        print(f"  [DEBUG] 隐含前提: {result.get('underlying_assumption')}")
        print(f"  [DEBUG] 哲学流派: {result.get('matched_philosophy')}")
        print(f"  [DEBUG] 对立流派: {result.get('opponent_philosophy')}")
        print(f"  [DEBUG] 对立理由: {result.get('opponent_core_argument')}")
        print(f"  [DEBUG] 反例攻击点: {result.get('rag_counter_example')}")
        print()


def main() -> None:
    # 加载 .env 环境变量
    load_dotenv()

    # 支持命令行参数单次执行模式，避免管道编码问题
    if len(sys.argv) > 1:
        _run_once(" ".join(sys.argv[1:]))
        return

    _, _, app = _init_llm_and_graph()

    print("=" * 50)
    print("  苏格拉底辩证智能体 — 社会公平")
    print("  输入你的观点，苏格拉底将向你提问。")
    print("  输入 quit 或 exit 退出。")
    print("=" * 50)
    print()

    turn_count = 0

    while True:
        try:
            user_input = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("再见！")
            break

        turn_count += 1

        # 执行图
        result = app.invoke({
            "user_input": user_input,
            "core_claim": "",
            "underlying_assumption": "",
            "matched_philosophy": "未知",
            "opponent_philosophy": "",
            "opponent_core_argument": "",
            "rag_counter_example": "",
            "socratic_question": "",
            "turn_count": turn_count,
        })

        # 输出苏格拉底提问
        question = result.get("socratic_question", "(未生成提问)")
        print(f"\n苏格拉底: {question}\n")

        # 可选: 展示中间推理 (调试用)
        if os.getenv("DEBUG", "").lower() in ("1", "true", "yes"):
            print(f"  [DEBUG] 核心主张: {result.get('core_claim')}")
            print(f"  [DEBUG] 隐含前提: {result.get('underlying_assumption')}")
            print(f"  [DEBUG] 哲学流派: {result.get('matched_philosophy')}")
            print(f"  [DEBUG] 反例攻击点: {result.get('rag_counter_example')}")
            print()


if __name__ == "__main__":
    main()
