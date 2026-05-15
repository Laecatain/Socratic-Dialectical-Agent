"""Phase 3 — 对抗性向量构建脚本

将 data/raw_texts.py 中的哲学语料分块、向量化，
并持久化存储到本地 ChromaDB（./chroma_db）。

每个 Chunk 携带 Metadata，包含 type 字段：
- claim：核心主张
- counter_example：反例攻击

用法：
    python ingest.py

前置条件：
    .env 文件中已配置：
    - EMBEDDING_API_KEY / OPENAI_API_KEY（优先 EMBEDDING_API_KEY）
    - EMBEDDING_API_BASE / OPENAI_API_BASE（优先 EMBEDDING_API_BASE）
    - EMBEDDING_MODEL_NAME（默认 text-embedding-3-small）
"""

import os
import sys

from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

from data.raw_texts import RAW_TEXTS

# ---------- 加载环境变量 ----------
load_dotenv()

# Embedding 专用配置：优先使用 EMBEDDING_* 环境变量，回退到 OPENAI_*
API_KEY = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY")
API_BASE = os.getenv("EMBEDDING_API_BASE") or os.getenv("OPENAI_API_BASE")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-3-small")
CHROMA_PERSIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")


def build_documents() -> list[Document]:
    """将 RAW_TEXTS 转换为 LangChain Document 对象。"""
    documents: list[Document] = []
    for content, metadata in RAW_TEXTS:
        documents.append(Document(page_content=content, metadata=metadata))
    print(f"[INFO] 加载了 {len(documents)} 篇原始文档。")
    return documents


def chunk_documents(documents: list[Document]) -> list[Document]:
    """使用 RecursiveCharacterTextSplitter 分割文档。

    每个分块自动继承原始文档的 metadata。
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,       # 每个分块最大 500 字符
        chunk_overlap=100,    # 相邻分块重叠 100 字符，保持语义连贯
        separators=["\n\n", "\n", "。", "？", "！", "；", " ", ""],
        length_function=len,
    )
    chunks = text_splitter.split_documents(documents)
    print(f"[INFO] 分块完成，共产生 {len(chunks)} 个 Chunk。")

    # 打印简要统计
    for chunk in chunks:
        print(
            f"  - type={chunk.metadata.get('type'):<16s} "
            f"philosophy={chunk.metadata.get('philosophy'):<8s} "
            f"len={len(chunk.page_content)}"
        )
    return chunks


def init_embeddings() -> OpenAIEmbeddings:
    """初始化 OpenAI Embeddings，使用兼容 API 网关。

    优先读取 EMBEDDING_API_KEY / EMBEDDING_API_BASE，
    未设置时回退到 OPENAI_API_KEY / OPENAI_API_BASE。
    """
    if not API_KEY:
        sys.exit("[ERROR] 未设置 EMBEDDING_API_KEY 或 OPENAI_API_KEY，请在 .env 文件中配置。")

    kwargs: dict = {
        "model": EMBEDDING_MODEL,
        "api_key": API_KEY,
    }
    # 对于非 OpenAI 兼容网关，需要禁用 token 拆分（如 DashScope）
    kwargs["check_embedding_ctx_length"] = False
    if API_BASE:
        base = API_BASE.rstrip("/")
        if not base.endswith("/v1"):
            base += "/v1"
        kwargs["base_url"] = base

    print(f"[INFO] Embedding 模型: {EMBEDDING_MODEL}")
    if kwargs.get("base_url"):
        print(f"[INFO] Embedding API Base: {kwargs['base_url']}")
    return OpenAIEmbeddings(**kwargs)


def ingest_to_chroma(chunks: list[Document], embeddings: OpenAIEmbeddings) -> Chroma:
    """将分块文档写入 ChromaDB 并持久化。"""
    print(f"[INFO] 正在写入 ChromaDB -> {CHROMA_PERSIST_DIR}")

    try:
        vector_store = Chroma.from_documents(
            documents=chunks,
            embedding=embeddings,
            persist_directory=CHROMA_PERSIST_DIR,
            collection_name="socratic_social_justice",
            collection_metadata={"hnsw:space": "cosine"},
        )
        print(f"[INFO] 成功写入 {vector_store._collection.count()} 条向量。")
        return vector_store
    except Exception as e:
        sys.exit(f"[ERROR] ChromaDB 写入失败: {e}")


def main() -> None:
    """主流程：加载 -> 分块 -> 向量化 -> 持久化。"""
    print("=" * 50)
    print("  Socratic Dialectical Agent — 语料入库")
    print("=" * 50)
    print()

    # 1. 构建文档
    documents = build_documents()

    # 2. 分块
    chunks = chunk_documents(documents)

    # 3. 初始化 Embedding
    embeddings = init_embeddings()

    # 4. 写入 ChromaDB
    ingest_to_chroma(chunks, embeddings)

    print()
    print("[SUCCESS] 入库完成。ChromaDB 数据目录: ./chroma_db")


if __name__ == "__main__":
    main()
