"""苏格拉底辩证智能体 — FastAPI SSE 流式后端（多轮记忆版）"""

import json
import logging
import os
import asyncio
import time
import uuid
from collections import defaultdict
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import BaseModel, Field

import sys
import io

# Force UTF-8 on Windows to avoid charmap encoding errors
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from graph import build_graph

load_dotenv()

app = FastAPI(title="Socratic Dialectical Agent API", version="2.0.0")

# ---------- 简易速率限制 ----------

_RATE_LIMIT_WINDOW = 60       # 60 秒窗口
_RATE_LIMIT_MAX_REQUESTS = 10  # 每窗口最多 10 次请求
_rate_limit_buckets: dict[str, list[float]] = defaultdict(list)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path == "/api/v1/socratic/stream":
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        bucket = _rate_limit_buckets[client_ip]
        # 清理过期记录
        bucket[:] = [t for t in bucket if now - t < _RATE_LIMIT_WINDOW]
        if len(bucket) >= _RATE_LIMIT_MAX_REQUESTS:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=429,
                content={"detail": "请求过于频繁，请稍后再试。"},
            )
        bucket.append(now)
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _init_llm_and_graph():
    api_key = os.getenv("OPENAI_API_KEY")
    api_base = os.getenv("OPENAI_API_BASE")
    model_name = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")

    embed_api_key = os.getenv("EMBEDDING_API_KEY") or api_key
    embed_api_base = os.getenv("EMBEDDING_API_BASE") or api_base
    embed_model = os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-3-small")

    if not api_key:
        raise RuntimeError("未设置 OPENAI_API_KEY。请在 .env 文件中配置。")

    llm = ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=api_base,
        temperature=0.7,
    )

    embed_kwargs: dict = {
        "model": embed_model,
        "api_key": embed_api_key,
    }
    embed_kwargs["check_embedding_ctx_length"] = False
    if embed_api_base:
        base = embed_api_base.rstrip("/")
        if not base.endswith("/v1"):
            base += "/v1"
        embed_kwargs["base_url"] = base
    embeddings = OpenAIEmbeddings(**embed_kwargs)

    graph = build_graph(llm, embeddings)
    return graph


_graph = _init_llm_and_graph()


class SocraticRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000, description="用户输入文本")
    thread_id: str = Field(default="", max_length=64, description="多轮会话ID")


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _empty_state(user_input: str, turn_count: int) -> dict:
    """构建初始状态字典。"""
    return {
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
        "turn_count": turn_count,
        "admitted_premises": [],
        "has_contradiction": False,
        "contradiction_details": None,
        "target_premise_id": None,
        "target_premise_statement": None,
        "target_premise_turn": None,
    }


async def _stream_socratic(user_input: str, thread_id: str) -> AsyncGenerator[str, None]:
    config = {"configurable": {"thread_id": thread_id}}

    # 从 checkpointer 恢复 turn_count（若为已有会话）
    try:
        current_state = _graph.get_state(config)
        prev_turn = current_state.values.get("turn_count", 0) if current_state.values else 0
    except Exception:
        prev_turn = 0

    initial_state = _empty_state(user_input, prev_turn + 1)

    yield _sse_event("status", {
        "phase": "started",
        "message": "开始分析...",
        "thread_id": thread_id,
        "turn": prev_turn + 1,
    })

    current_node = None
    intermediate_data: dict = {}

    try:
        async for event in _graph.astream_events(initial_state, config, version="v2"):
            kind = event.get("event")
            name = event.get("name")

            if kind == "on_chain_start" and name in (
                "Analyzer", "Retriever", "Web_Search", "Socratic_Ironist"
            ):
                current_node = name
                node_labels = {
                    "Analyzer": "正在提取核心主张...",
                    "Retriever": "正在检索反例...",
                    "Web_Search": "正在搜索网络反例...",
                    "Socratic_Ironist": "正在生成苏格拉底式提问...",
                }
                yield _sse_event(
                    "node_start",
                    {"node": name, "message": node_labels.get(name, name)}
                )

            elif kind == "on_chain_end" and name in (
                "Analyzer", "Retriever", "Web_Search", "Socratic_Ironist"
            ):
                output = event.get("data", {}).get("output", {})
                intermediate_data[name] = output
                yield _sse_event(
                    "node_end",
                    {"node": name, "output": output}
                )
                current_node = None

            elif kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    token_text = chunk.content
                    metadata = event.get("metadata", {})
                    node_from_meta = metadata.get("langgraph_node", "")

                    if node_from_meta == "Socratic_Ironist" or current_node == "Socratic_Ironist":
                        yield _sse_event("token", {"content": token_text})

        analyzer_output = intermediate_data.get("Analyzer", {})
        socratic_q = intermediate_data.get("Socratic_Ironist", {}).get(
            "socratic_question", ""
        )

        yield _sse_event(
            "done",
            {
                "socratic_question": socratic_q,
                "core_claim": analyzer_output.get("core_claim", ""),
                "philosophy": analyzer_output.get("matched_philosophy", "未知"),
                "opponent_philosophy": analyzer_output.get("opponent_philosophy", ""),
                "opponent_core_argument": analyzer_output.get("opponent_core_argument", ""),
                "has_contradiction": analyzer_output.get("has_contradiction", False),
                "contradiction_details": analyzer_output.get("contradiction_details"),
                "target_premise_id": analyzer_output.get("target_premise_id"),
                "turn": prev_turn + 1,
            }
        )
        yield "data: [DONE]\n\n"

    except Exception as e:
        logging.exception("Socratic stream error")
        yield _sse_event("error", {"message": "处理请求时发生内部错误，请稍后重试。"})


@app.post("/api/v1/socratic/stream")
async def socratic_stream(req: SocraticRequest, request: Request):
    # 使用前端传入的 thread_id 或自动生成新会话
    thread_id = req.thread_id.strip() if req.thread_id else f"web_{uuid.uuid4().hex[:8]}"

    async def event_generator():
        disconnected = False

        async def check_disconnect():
            nonlocal disconnected
            while not disconnected:
                if await request.is_disconnected():
                    disconnected = True
                    return
                await asyncio.sleep(0.5)

        disconnect_task = asyncio.create_task(check_disconnect())

        try:
            async for chunk in _stream_socratic(req.text, thread_id):
                if disconnected:
                    break
                yield chunk
        finally:
            disconnect_task.cancel()
            try:
                await disconnect_task
            except asyncio.CancelledError:
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/health")
async def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
