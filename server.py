"""苏格拉底辩证智能体 — FastAPI SSE 流式后端"""

import json
import os
import asyncio
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import BaseModel

import sys
import io

# Force UTF-8 on Windows to avoid charmap encoding errors
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from graph import build_graph

load_dotenv()

app = FastAPI(title="Socratic Dialectical Agent API", version="1.0.0")

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
    text: str
    context_url: str = ""


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _stream_socratic(user_input: str) -> AsyncGenerator[str, None]:
    initial_state = {
        "user_input": user_input,
        "core_claim": "",
        "underlying_assumption": "",
        "matched_philosophy": "未知",
        "rag_counter_example": "",
        "socratic_question": "",
        "turn_count": 1,
    }

    yield _sse_event("status", {"phase": "started", "message": "开始分析..."})

    current_node = None
    intermediate_data: dict = {}

    try:
        async for event in _graph.astream_events(initial_state, version="v2"):
            kind = event.get("event")
            name = event.get("name")

            if kind == "on_chain_start" and name in (
                "Analyzer", "Retriever", "Socratic_Ironist"
            ):
                current_node = name
                node_labels = {
                    "Analyzer": "正在提取核心主张...",
                    "Retriever": "正在检索反例...",
                    "Socratic_Ironist": "正在生成苏格拉底式提问...",
                }
                yield _sse_event(
                    "node_start",
                    {"node": name, "message": node_labels.get(name, name)}
                )

            elif kind == "on_chain_end" and name in (
                "Analyzer", "Retriever", "Socratic_Ironist"
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

        socratic_q = intermediate_data.get("Socratic_Ironist", {}).get(
            "socratic_question", ""
        )
        yield _sse_event(
            "done",
            {
                "socratic_question": socratic_q,
                "core_claim": intermediate_data.get("Analyzer", {}).get("core_claim", ""),
                "philosophy": intermediate_data.get("Analyzer", {}).get("matched_philosophy", "未知"),
            }
        )
        yield "data: [DONE]\n\n"

    except Exception as e:
        yield _sse_event("error", {"message": str(e)})


@app.post("/api/v1/socratic/stream")
async def socratic_stream(req: SocraticRequest, request: Request):
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
            async for chunk in _stream_socratic(req.text):
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
