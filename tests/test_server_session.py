import asyncio
import importlib
import json
import sys
import time
from collections.abc import AsyncGenerator
from http.cookies import SimpleCookie
from typing import Any

import pytest


class FakeRequest:
    def __init__(self, cookies: dict[str, str] | None = None):
        self.cookies = cookies or {}

    async def is_disconnected(self) -> bool:
        return False


async def collect_stream_response(response) -> str:
    chunks: list[str] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
    return "".join(chunks)


def response_cookie(response, name: str) -> str | None:
    for key, value in response.raw_headers:
        if key.lower() == b"set-cookie":
            cookie = SimpleCookie(value.decode())
            if name in cookie:
                return cookie[name].value
    return None


async def call_stream(server_module, text: str, thread_id: str, cookies: dict[str, str] | None = None):
    response = await server_module.socratic_stream(
        server_module.SocraticRequest(text=text, thread_id=thread_id),
        FakeRequest(cookies),
    )
    body = await collect_stream_response(response)
    return response, body


@pytest.fixture()
def server_module(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_BASE", "http://example.invalid/v1")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("ENVIRONMENT", "test")

    if "server" in sys.modules:
        del sys.modules["server"]

    module = importlib.import_module("server")

    class FakeGraph:
        def get_state(self, _config: dict[str, Any]):
            return type("State", (), {"values": {}})()

    module._graph = FakeGraph()
    module._rate_limit_buckets.clear()
    yield module
    sys.modules.pop("server", None)


def test_sanitize_client_thread_id_accepts_frontend_uuid_style(server_module):
    raw = "web_123e4567-e89b-12d3-a456-426614174000"

    assert server_module._sanitize_client_thread_id(raw) == raw


def test_sanitize_client_thread_id_rejects_unsafe_chars(server_module):
    sanitized = server_module._sanitize_client_thread_id("../bad\nthread")

    assert sanitized == "default"
    assert ".." not in sanitized
    assert "\n" not in sanitized


def test_owned_thread_id_is_stable_for_same_session_and_thread(server_module):
    first = server_module._derive_owned_thread_id("session-a", "web_thread")
    second = server_module._derive_owned_thread_id("session-a", "web_thread")

    assert first == second
    assert first != "web_thread"


def test_owned_thread_id_changes_when_session_changes(server_module):
    first = server_module._derive_owned_thread_id("session-a", "web_thread")
    second = server_module._derive_owned_thread_id("session-b", "web_thread")

    assert first != second


def test_stream_endpoint_sets_session_cookie_and_uses_owned_thread_id(
    server_module,
    monkeypatch: pytest.MonkeyPatch,
):
    seen_thread_ids: list[str] = []

    async def fake_stream(_text: str, thread_id: str) -> AsyncGenerator[str, None]:
        seen_thread_ids.append(thread_id)
        yield server_module._sse_event("done", {"socratic_question": "好", "turn": 1})
        yield "data: [DONE]\n\n"

    monkeypatch.setattr(server_module, "_stream_socratic", fake_stream)

    response, body = asyncio.run(
        call_stream(server_module, "测试", "web_123e4567-e89b-12d3-a456-426614174000")
    )

    assert response.status_code == 200
    assert "data: [DONE]" in body
    signed_cookie = response_cookie(response, server_module.SESSION_COOKIE_NAME)
    assert signed_cookie
    cookie = server_module._verify_session_cookie(signed_cookie)
    assert cookie
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=lax" in response.headers["set-cookie"].lower()
    assert seen_thread_ids == [
        server_module._derive_owned_thread_id(cookie, "web_123e4567-e89b-12d3-a456-426614174000")
    ]


def test_stream_endpoint_reuses_existing_session_cookie(server_module, monkeypatch: pytest.MonkeyPatch):
    seen_thread_ids: list[str] = []

    async def fake_stream(_text: str, thread_id: str) -> AsyncGenerator[str, None]:
        seen_thread_ids.append(thread_id)
        yield server_module._sse_event("done", {"socratic_question": "好", "turn": 1})
        yield "data: [DONE]\n\n"

    monkeypatch.setattr(server_module, "_stream_socratic", fake_stream)

    response, body = asyncio.run(
        call_stream(
            server_module,
            "测试",
            "web_same",
            {server_module.SESSION_COOKIE_NAME: server_module._sign_session_id("existing-session")},
        )
    )

    assert response.status_code == 200
    assert "data: [DONE]" in body
    assert response_cookie(response, server_module.SESSION_COOKIE_NAME) is None
    assert seen_thread_ids == [server_module._derive_owned_thread_id("existing-session", "web_same")]


def test_unsigned_session_cookie_is_replaced(server_module, monkeypatch: pytest.MonkeyPatch):
    seen_thread_ids: list[str] = []

    async def fake_stream(_text: str, thread_id: str) -> AsyncGenerator[str, None]:
        seen_thread_ids.append(thread_id)
        yield server_module._sse_event("done", {"socratic_question": "好", "turn": 1})
        yield "data: [DONE]\n\n"

    monkeypatch.setattr(server_module, "_stream_socratic", fake_stream)

    response, body = asyncio.run(
        call_stream(
            server_module,
            "测试",
            "web_same",
            {server_module.SESSION_COOKIE_NAME: "attacker-fixed"},
        )
    )

    assert response.status_code == 200
    assert "data: [DONE]" in body
    signed_cookie = response_cookie(response, server_module.SESSION_COOKIE_NAME)
    assert signed_cookie
    verified_cookie = server_module._verify_session_cookie(signed_cookie)
    assert verified_cookie and verified_cookie != "attacker-fixed"
    assert seen_thread_ids == [server_module._derive_owned_thread_id(verified_cookie, "web_same")]


def test_sanitize_client_thread_id_uses_stable_default_for_blank_values(server_module):
    assert server_module._sanitize_client_thread_id("") == "default"
    assert server_module._sanitize_client_thread_id(None) == "default"


def test_sse_event_truncates_large_string_fields(server_module):
    event = server_module._sse_event("done", {"socratic_question": "x" * 9000})
    data = event.split("data: ", 1)[1].strip()

    assert len(json.loads(data)["socratic_question"]) == server_module.MAX_SERVER_SSE_FIELD_LENGTH


def test_signed_session_cookie_expires_server_side(server_module, monkeypatch: pytest.MonkeyPatch):
    session_id = "expired-session"
    expires_at = int(time.time()) - 1
    payload = f"{session_id}:{expires_at}"
    signature = server_module.hmac.new(
        server_module._session_secret(),
        payload.encode("utf-8"),
        server_module.hashlib.sha256,
    ).hexdigest()

    assert server_module._verify_session_cookie(f"{payload}.{signature}") is None


def test_session_secret_is_required_outside_local_env(server_module, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        server_module._session_secret()


def test_build_initial_state_preserves_admitted_premises(server_module):
    previous_premises = [{"premise_id": "PREMISE_001", "statement": "自由优先"}]

    state = server_module._build_initial_state(
        "新问题",
        {"turn_count": 3, "admitted_premises": previous_premises},
    )

    assert state["turn_count"] == 4
    assert state["admitted_premises"] == previous_premises


def test_stream_socratic_emits_sanitized_error_when_graph_init_fails(server_module, monkeypatch: pytest.MonkeyPatch):
    def fail_graph():
        raise RuntimeError("secret provider details")

    monkeypatch.setattr(server_module, "_get_graph", fail_graph)

    async def collect():
        return [chunk async for chunk in server_module._stream_socratic("测试", "thread")]

    chunks = asyncio.run(collect())

    assert chunks == [server_module._sse_event("error", {"message": "处理请求时发生内部错误，请稍后重试。"})]


def test_expiring_at_current_second_is_invalid(server_module, monkeypatch: pytest.MonkeyPatch):
    session_id = "boundary-session"
    expires_at = int(time.time())
    payload = f"{session_id}:{expires_at}"
    signature = server_module.hmac.new(
        server_module._session_secret(),
        payload.encode("utf-8"),
        server_module.hashlib.sha256,
    ).hexdigest()

    assert server_module._verify_session_cookie(f"{payload}.{signature}") is None


def test_state_load_error_emits_sanitized_stream_error(server_module, monkeypatch: pytest.MonkeyPatch):
    class FailingGraph:
        def get_state(self, _config: dict[str, Any]):
            raise RuntimeError("checkpointer secret")

    monkeypatch.setattr(server_module, "_get_graph", lambda: FailingGraph())

    async def collect():
        return [chunk async for chunk in server_module._stream_socratic("测试", "thread")]

    chunks = asyncio.run(collect())

    assert chunks == [server_module._sse_event("error", {"message": "处理请求时发生内部错误，请稍后重试。"})]


def test_build_initial_state_copies_admitted_premises(server_module):
    previous_premises = [{"premise_id": "PREMISE_001", "statement": "自由优先"}]

    state = server_module._build_initial_state(
        "新问题",
        {"turn_count": 3, "admitted_premises": previous_premises},
    )

    assert state["admitted_premises"] == previous_premises
    assert state["admitted_premises"] is not previous_premises
    assert state["admitted_premises"][0] is not previous_premises[0]


def test_sse_event_remains_json_encoded(server_module):
    event = server_module._sse_event("done", {"socratic_question": "好"})
    data = event.split("data: ", 1)[1].strip()

    assert json.loads(data) == {"socratic_question": "好"}
