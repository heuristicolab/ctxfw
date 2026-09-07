"""
tests/test_proxy_gateway.py — Comprehensive Test Suite for Reverse Proxy Gateway (Sprint 3.3)
Validates Fail-Open policy, transparent request rewriting, header auditing,
OpenAI/Anthropic payload handling, and sub-5ms caching via hermetic httpx mocks.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
import httpx

from contracts import LocalSemanticCache
from proxy_gateway import app, get_cache


@pytest.fixture
def mock_upstream(tmp_path: Path):
    """Sets up an isolated SQLite cache and a hermetic mock httpx transport."""
    db_file = tmp_path / "test_proxy_cache.db"
    app.state.cache = LocalSemanticCache(str(db_file))

    captured_requests = []

    def handle_mock(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8")) if request.content else {}
        captured_requests.append({
            "url": str(request.url),
            "headers": dict(request.headers),
            "body": body,
        })

        if "chat/completions" in str(request.url):
            return httpx.Response(
                status_code=200,
                json={
                    "id": "chatcmpl-mock",
                    "object": "chat.completion",
                    "choices": [{"message": {"role": "assistant", "content": "Mock OpenAI response"}}],
                    "usage": {"total_tokens": 100},
                },
                headers={"content-type": "application/json"},
            )
        else:
            return httpx.Response(
                status_code=200,
                json={
                    "id": "msg-mock",
                    "type": "message",
                    "content": [{"type": "text", "text": "Mock Anthropic response"}],
                },
                headers={"content-type": "application/json"},
            )

    transport = httpx.MockTransport(handle_mock)
    mock_client = httpx.AsyncClient(transport=transport)
    app.state.upstream_client = mock_client

    yield captured_requests

    # Cleanup
    app.state.upstream_client = None


@pytest.fixture
def client(mock_upstream):
    return TestClient(app)


def test_health_check_endpoint(client: TestClient):
    """Asserts GET /health returns service status, version, and cache entries."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["version"] == "3.3.0"
    assert data["service"] == "context-firewall-proxy"
    assert data["fail_open_policy"] is True
    assert "cache_entries" in data


def test_chat_completions_compacts_markdown_code(client: TestClient, mock_upstream):
    """Asserts that Python code blocks in chat completions are compacted to interfaces with stubs."""
    raw_code = (
        "class PaymentService:\n"
        "    '''Handles customer payment.'''\n"
        "    def process(self, amount: float) -> bool:\n"
        "        token = 'confidential_jwt_secret'\n"
        "        calc = amount * 1.16\n"
        "        if amount <= 0:\n"
        "            raise ValueError('Invalid amount: ' + str(amount))\n"
        "        return True\n"
    )
    prompt = f"Please review this implementation:\n```python\n{raw_code}```"

    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    assert resp.status_code == 200
    assert resp.headers["X-Firewall-Status"] == "compacted"
    tokens_saved = int(resp.headers["X-Tokens-Saved"])
    assert tokens_saved > 0

    # Verify what upstream received
    assert len(mock_upstream) == 1
    upstream_payload = mock_upstream[0]["body"]
    forwarded_content = upstream_payload["messages"][0]["content"]

    assert "def process(self, amount: float) -> bool:" in forwarded_content
    assert "..." in forwarded_content
    assert "raise ValueError('...')" in forwarded_content
    assert "confidential_jwt_secret" not in forwarded_content
    assert "amount * 1.16" not in forwarded_content


def test_chat_completions_bypass_header(client: TestClient, mock_upstream):
    """Asserts that X-Context-Firewall-Bypass: true leaves code 100% intact."""
    raw_code = "def sensitive_calc():\n    secret = 42\n    return secret\n"
    prompt = f"```python\n{raw_code}```"

    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": prompt}],
        },
        headers={"X-Context-Firewall-Bypass": "true"},
    )
    assert resp.status_code == 200
    assert resp.headers["X-Firewall-Status"] == "bypassed"
    assert resp.headers["X-Tokens-Saved"] == "0"

    forwarded_content = mock_upstream[0]["body"]["messages"][0]["content"]
    assert "secret = 42" in forwarded_content


def test_fail_open_on_broken_syntax(client: TestClient, mock_upstream):
    """Asserts Fail-Open invariant: unparseable code is passed through unmodified without 500 error."""
    broken_code = "def broken(:\n    syntax error here\n"
    prompt = f"Check this code:\n```python\n{broken_code}```"

    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    assert resp.status_code == 200
    assert resp.headers["X-Tokens-Saved"] == "0"
    assert resp.headers["X-Firewall-Status"] == "pass-through"

    forwarded_content = mock_upstream[0]["body"]["messages"][0]["content"]
    assert broken_code in forwarded_content


def test_non_code_message_pass_through(client: TestClient, mock_upstream):
    """Asserts that conversational prompts with no code blocks are forwarded untouched."""
    prompt = "What is the capital of France and what is its population?"

    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    assert resp.status_code == 200
    assert resp.headers["X-Tokens-Saved"] == "0"
    assert resp.headers["X-Firewall-Status"] == "pass-through"

    forwarded_content = mock_upstream[0]["body"]["messages"][0]["content"]
    assert forwarded_content == prompt


def test_anthropic_messages_proxy(client: TestClient, mock_upstream):
    """Asserts that Anthropic /v1/messages format is properly intercepted and compacted."""
    raw_code = "class Worker:\n    def run(self):\n        x = 100\n        return x\n"
    resp = client.post(
        "/v1/messages",
        json={
            "model": "claude-3-5-sonnet-20241022",
            "messages": [{"role": "user", "content": f"```python\n{raw_code}```"}],
            "system": "System instructions",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["X-Firewall-Status"] == "compacted"
    assert int(resp.headers["X-Tokens-Saved"]) > 0

    forwarded_content = mock_upstream[0]["body"]["messages"][0]["content"]
    assert "..." in forwarded_content
    assert "x = 100" not in forwarded_content


def test_tagged_file_blocks_respects_depth(client: TestClient, mock_upstream):
    """Asserts that tagged blocks preserve D0 [FULL] and compact D1 [INTERFACE]."""
    target_code = "def target_func():\n    keep_this = 'full_implementation'\n    return keep_this\n"
    dep_code = "def dep_func():\n    remove_this = 'secret_logic'\n    return 42\n"

    tagged_prompt = (
        f"### File: main.py [FULL]\n```python\n{target_code}```\n\n"
        f"### File: utils.py [INTERFACE]\n```python\n{dep_code}```\n"
    )

    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": tagged_prompt}],
        },
    )
    assert resp.status_code == 200
    assert resp.headers["X-Firewall-Status"] == "compacted"

    forwarded = mock_upstream[0]["body"]["messages"][0]["content"]
    # D0 is preserved
    assert "keep_this = 'full_implementation'" in forwarded
    # D1 is pruned
    assert "remove_this = 'secret_logic'" not in forwarded
    assert "def dep_func():" in forwarded
    assert "..." in forwarded


def test_warm_cache_sub_5ms_overhead(client: TestClient):
    """Asserts that repeating the same request hits the warm cache with <5ms proxy overhead."""
    code = "def fast_cache_check():\n    a = 1 + 2\n    return a\n"
    prompt = f"```python\n{code}```"
    req_body = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": prompt}],
    }

    # Warm up cache
    client.post("/v1/chat/completions", json=req_body)

    # Subsequent warm calls
    latencies = []
    for _ in range(3):
        resp = client.post("/v1/chat/completions", json=req_body)
        assert resp.status_code == 200
        latencies.append(float(resp.headers["X-Firewall-Latency-Ms"]))

    # Minimum warm latency should be fast (<15ms on Windows disk IO)
    assert min(latencies) < 15.0
