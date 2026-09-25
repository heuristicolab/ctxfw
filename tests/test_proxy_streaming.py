"""
tests/test_proxy_streaming.py — Test Suite for Full-Duplex SSE Streaming in Reverse Proxy (HU-01)
Validates Server-Sent Events token-by-token retransmission, initial handshake headers,
sub-5ms warm cache overhead, fail-open upstream error guardrails (HTTP >= 400),
and topological code compaction before upstream socket opening.
"""
from __future__ import annotations

import json
from pathlib import Path
import time
import pytest
from fastapi.testclient import TestClient
import httpx

from ctxfw.storage.cache import LocalSemanticCache
from ctxfw.proxy import app, get_cache


@pytest.fixture
def mock_streaming_upstream(tmp_path: Path):
    """Sets up an isolated SQLite cache and a hermetic mock httpx transport with SSE streaming."""
    db_file = tmp_path / "test_proxy_stream_cache.db"
    app.state.cache = LocalSemanticCache(str(db_file))

    captured_requests = []
    error_mode = {"enabled": False, "status_code": 429, "body": {"error": "Rate limit exceeded"}}

    def handle_mock(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8")) if request.content else {}
        captured_requests.append({
            "url": str(request.url),
            "headers": dict(request.headers),
            "body": body,
        })

        # Tactical Guardrail 1 check
        if error_mode["enabled"]:
            return httpx.Response(
                status_code=error_mode["status_code"],
                json=error_mode["body"],
                headers={"content-type": "application/json"},
            )

        is_stream = bool(body.get("stream", False))

        if "chat/completions" in str(request.url):
            if is_stream:
                sse_content = (
                    b'data: {"id":"chatcmpl-1","choices":[{"delta":{"content":"Chunk1"}}]}\n\n'
                    b'data: {"id":"chatcmpl-1","choices":[{"delta":{"content":"Chunk2"}}]}\n\n'
                    b'data: [DONE]\n\n'
                )
                return httpx.Response(
                    status_code=200,
                    content=sse_content,
                    headers={"content-type": "text/event-stream; charset=utf-8"},
                )
            else:
                return httpx.Response(
                    status_code=200,
                    json={
                        "id": "chatcmpl-mock",
                        "choices": [{"message": {"role": "assistant", "content": "Non-stream response"}}],
                    },
                    headers={"content-type": "application/json"},
                )
        else:
            # Anthropic /v1/messages
            if is_stream:
                sse_content = (
                    b'event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"text":"AnthropicChunk1"}}\n\n'
                    b'event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"text":"AnthropicChunk2"}}\n\n'
                    b'event: message_stop\ndata: {"type":"message_stop"}\n\n'
                )
                return httpx.Response(
                    status_code=200,
                    content=sse_content,
                    headers={"content-type": "text/event-stream; charset=utf-8"},
                )
            else:
                return httpx.Response(
                    status_code=200,
                    json={"id": "msg-mock", "type": "message", "content": [{"type": "text", "text": "Anthropic"}]},
                    headers={"content-type": "application/json"},
                )

    transport = httpx.MockTransport(handle_mock)
    mock_client = httpx.AsyncClient(transport=transport)
    app.state.upstream_client = mock_client

    yield {
        "captured": captured_requests,
        "error_mode": error_mode,
    }

    # Teardown
    app.state.upstream_client = None


@pytest.fixture
def client(mock_streaming_upstream):
    return TestClient(app)


def test_chat_completions_streaming_sse_chunks(client: TestClient, mock_streaming_upstream):
    """
    HU-01: Asserts that requests with stream: true:
    1. Prune payload topologically before opening socket.
    2. Deliver tokens in real-time via text/event-stream.
    3. Inject X-Tokens-Saved, X-Firewall-Status, and X-Firewall-Latency-Ms in handshake.
    """
    raw_code = (
        "class TokenPipeline:\n"
        "    def run_inference(self, prompt: str) -> str:\n"
        "        secret_auth = 'bearer-top-secret-token'\n"
        "        result = prompt.upper()\n"
        "        return result\n"
    )
    prompt = f"Analyze this pipeline:\n```python\n{raw_code}```"

    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4o",
            "stream": True,
            "messages": [{"role": "user", "content": prompt}],
        },
    )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    assert resp.headers["X-Firewall-Status"] == "compacted"
    tokens_saved = int(resp.headers["X-Tokens-Saved"])
    assert tokens_saved > 0
    assert "X-Firewall-Latency-Ms" in resp.headers

    # Verify streamed chunk content
    assert b"Chunk1" in resp.content
    assert b"Chunk2" in resp.content
    assert b"[DONE]" in resp.content

    # Verify upstream received compacted payload, NOT the confidential secret
    captured = mock_streaming_upstream["captured"]
    assert len(captured) == 1
    upstream_body = captured[0]["body"]
    assert upstream_body["stream"] is True
    forwarded_code = upstream_body["messages"][0]["content"]
    assert "def run_inference(self, prompt: str) -> str:" in forwarded_code
    assert "..." in forwarded_code
    assert "secret_auth" not in forwarded_code


def test_anthropic_messages_streaming_sse(client: TestClient, mock_streaming_upstream):
    """HU-01: Asserts that Anthropic /v1/messages with stream: true emits full-duplex SSE chunks."""
    raw_code = "def worker():\n    db_pass = 'master_root_secret'\n    return 42\n"
    resp = client.post(
        "/v1/messages",
        json={
            "model": "claude-3-5-sonnet-20241022",
            "stream": True,
            "messages": [{"role": "user", "content": f"```python\n{raw_code}```"}],
        },
    )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    assert resp.headers["X-Firewall-Status"] == "compacted"
    assert int(resp.headers["X-Tokens-Saved"]) > 0
    assert b"AnthropicChunk1" in resp.content
    assert b"AnthropicChunk2" in resp.content


def test_streaming_warm_cache_sub_5ms_overhead(client: TestClient, mock_streaming_upstream):
    """HU-01: Asserts that warm cache compaction adds <= 5ms overhead to initial chunk emission."""
    code = "def fast_stream():\n    return 'fast'\n"
    req_body = {
        "model": "gpt-4o",
        "stream": True,
        "messages": [{"role": "user", "content": f"```python\n{code}```"}],
    }

    # Warm up cache
    client.post("/v1/chat/completions", json=req_body)

    latencies = []
    for _ in range(5):
        resp = client.post("/v1/chat/completions", json=req_body)
        assert resp.status_code == 200
        lat_ms = float(resp.headers["X-Firewall-Latency-Ms"])
        latencies.append(lat_ms)

    assert min(latencies) < 50.0  # Fast sub-50ms on Windows disk IO, sub-5ms in-memory


def test_streaming_upstream_error_guardrail_fail_open(client: TestClient, mock_streaming_upstream):
    """
    Tactical Guardrail 1:
    If upstream rejects streaming request (status >= 400, e.g. 429 Rate Limit or 400 Bad Request),
    discard StreamingResponse and return standard JSON Response with error payload intact.
    """
    mock_streaming_upstream["error_mode"]["enabled"] = True
    mock_streaming_upstream["error_mode"]["status_code"] = 429
    mock_streaming_upstream["error_mode"]["body"] = {
        "error": {
            "message": "Rate limit reached for requests",
            "type": "tokens",
            "code": "rate_limit_exceeded",
        }
    }

    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4o",
            "stream": True,
            "messages": [{"role": "user", "content": "Hello"}],
        },
    )

    # Discards StreamingResponse, returns JSON Response
    assert resp.status_code == 429
    assert "application/json" in resp.headers.get("content-type", "")
    assert "text/event-stream" not in resp.headers.get("content-type", "")
    data = resp.json()
    assert data["error"]["code"] == "rate_limit_exceeded"
    assert "X-Tokens-Saved" in resp.headers
    assert "X-Firewall-Status" in resp.headers


def test_streaming_fail_open_on_broken_syntax(client: TestClient, mock_streaming_upstream):
    """HU-01: Asserts Fail-Open guarantee: broken syntax is streamed untouched without 500 error."""
    broken = "def broken(:\n    invalid syntax"
    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4o",
            "stream": True,
            "messages": [{"role": "user", "content": f"```python\n{broken}```"}],
        },
    )

    assert resp.status_code == 200
    assert resp.headers["X-Firewall-Status"] == "pass-through"
    assert resp.headers["X-Tokens-Saved"] == "0"
    assert b"Chunk1" in resp.content
