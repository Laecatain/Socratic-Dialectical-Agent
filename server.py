"""苏格拉底辩证智能体 — FastAPI SSE 流式后端（多轮记忆版）"""

import asyncio
import copy
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sys
import time
from collections import defaultdict
from typing import Any, AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import BaseModel, Field


# Force UTF-8 on Windows to avoid charmap encoding errors
if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

from graph import build_graph

load_dotenv()

app = FastAPI(title="Socratic Dialectical Agent API", version="2.0.0")

# ---------- 简易速率限制 ----------

_RATE_LIMIT_WINDOW = 60  # 60 秒窗口
_RATE_LIMIT_MAX_REQUESTS = 10  # 每窗口最多 10 次请求
_rate_limit_buckets: dict[str, list[float]] = defaultdict(list)

SESSION_COOKIE_NAME = "socratic_session"
SESSION_COOKIE_MAX_AGE = 60 * 60 * 24 * 30
MAX_SERVER_SSE_FIELD_LENGTH = 8000
_CLIENT_THREAD_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_LOCAL_ENVIRONMENTS = {"development", "local", "test"}
_graph: Any | None = None


def _truncate_sse_text(value: Any) -> Any:
    if isinstance(value, str):
        return value[:MAX_SERVER_SSE_FIELD_LENGTH]
    if isinstance(value, dict):
        return {key: _truncate_sse_text(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_truncate_sse_text(item) for item in value]
    return value


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
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
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


def _get_graph():
    global _graph
    if _graph is None:
        _graph = _init_llm_and_graph()
    return _graph


def _is_local_development() -> bool:
    return os.getenv("ENVIRONMENT", "").lower() in _LOCAL_ENVIRONMENTS


def _session_secret() -> bytes:
    secret = os.getenv("SESSION_SECRET")
    if not secret:
        if _is_local_development():
            secret = "local-dev-session-secret"
        else:
            raise RuntimeError("未设置 SESSION_SECRET。请为会话签名配置独立密钥。")
    return secret.encode("utf-8")


def _sign_session_id(session_id: str) -> str:
    expires_at = int(time.time()) + SESSION_COOKIE_MAX_AGE
    payload = f"{session_id}:{expires_at}"
    signature = hmac.new(_session_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def _verify_session_cookie(value: str) -> str | None:
    payload, separator, signature = value.partition(".")
    session_id, payload_separator, expires_at_text = payload.partition(":")
    if not separator or not payload_separator or not _is_valid_session_id(session_id):
        return None

    try:
        expires_at = int(expires_at_text)
    except ValueError:
        return None

    if expires_at <= int(time.time()):
        return None

    expected = hmac.new(_session_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if hmac.compare_digest(signature, expected):
        return session_id
    return None


def _new_session_id() -> str:
    return secrets.token_urlsafe(32)


def _is_valid_session_id(value: str) -> bool:
    return bool(value) and len(value) <= 128 and all(ch.isalnum() or ch in "-_" for ch in value)


def _get_or_create_session_id(request: Request) -> tuple[str, bool]:
    existing = request.cookies.get(SESSION_COOKIE_NAME, "")
    verified = _verify_session_cookie(existing)
    if verified:
        return verified, False
    return _new_session_id(), True


def _sanitize_client_thread_id(value: str | None) -> str:
    candidate = (value or "").strip()
    if _CLIENT_THREAD_ID_PATTERN.fullmatch(candidate):
        return candidate
    return "default"


def _derive_owned_thread_id(session_id: str, client_thread_id: str) -> str:
    session_digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:24]
    thread_digest = hashlib.sha256(client_thread_id.encode("utf-8")).hexdigest()[:24]
    return f"sess_{session_digest}_{thread_digest}"


class SocraticRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000, description="用户输入文本")
    thread_id: str = Field(default="", max_length=128, description="多轮会话ID")


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(_truncate_sse_text(data), ensure_ascii=False)}\n\n"


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


def _state_values(graph: Any, config: dict) -> dict:
    current_state = graph.get_state(config)
    return current_state.values if current_state.values else {}


def _build_initial_state(user_input: str, prev_state: dict) -> dict:
    state = _empty_state(user_input, int(prev_state.get("turn_count", 0)) + 1)
    state["admitted_premises"] = copy.deepcopy(prev_state.get("admitted_premises", []))
    return state


async def _stream_socratic(user_input: str, thread_id: str) -> AsyncGenerator[str, None]:
    try:
        graph = _get_graph()
        config = {"configurable": {"thread_id": thread_id}}
        prev_state = _state_values(graph, config)
        initial_state = _build_initial_state(user_input, prev_state)

        yield _sse_event("status", {
            "phase": "started",
            "message": "开始分析...",
            "thread_id": thread_id,
            "turn": initial_state["turn_count"],
        })

        current_node = None
        intermediate_data: dict = {}

        async for event in graph.astream_events(initial_state, config, version="v2"):
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
                "turn": initial_state["turn_count"],
            }
        )
        yield "data: [DONE]\n\n"

    except Exception:
        logging.exception("Socratic stream error")
        yield _sse_event("error", {"message": "处理请求时发生内部错误，请稍后重试。"})


@app.post("/api/v1/socratic/stream")
async def socratic_stream(req: SocraticRequest, request: Request):
    session_id, is_new_session = _get_or_create_session_id(request)
    client_thread_id = _sanitize_client_thread_id(req.thread_id)
    thread_id = _derive_owned_thread_id(session_id, client_thread_id)

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

    response = StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

    if is_new_session:
        response.set_cookie(
            SESSION_COOKIE_NAME,
            _sign_session_id(session_id),
            max_age=SESSION_COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=not _is_local_development(),
        )

    return response


@app.get("/health")
async def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
