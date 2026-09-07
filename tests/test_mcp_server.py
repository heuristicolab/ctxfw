"""
tests/test_mcp_server.py — Comprehensive Test Suite for MCP Server over stdio (Sprint 3.2)
Validates JSON-RPC 2.0 handshake, tool enumeration, context pruning,
topological bundle resolution, caching, stdio hygiene, and error shielding.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
import pytest

from contracts import LocalSemanticCache
from mcp_server import MCPServer


@pytest.fixture
def temp_cache(tmp_path: Path) -> LocalSemanticCache:
    """Provides an isolated LocalSemanticCache backed by a temporary SQLite database."""
    db_file = tmp_path / "test_mcp_cache.db"
    return LocalSemanticCache(str(db_file))


@pytest.fixture
def mcp_server(temp_cache: LocalSemanticCache) -> MCPServer:
    """Provides a fresh MCPServer instance configured with temp cache."""
    return MCPServer(cache=temp_cache)


@pytest.fixture
def multi_module_project(tmp_path: Path) -> Path:
    """Sets up a multi-module Python project for topological bundling tests."""
    proj = tmp_path / "sample_system"
    proj.mkdir()

    (proj / "app.py").write_text(
        "import worker\n\ndef start():\n    return worker.execute_job()\n",
        encoding="utf-8",
    )
    (proj / "worker.py").write_text(
        "class JobWorker:\n    '''Executes background tasks.'''\n    def execute_job(self) -> bool:\n        # sensitive logic\n        key = 'secret_key_12345'\n        if not key:\n            raise ValueError('Missing key: ' + key)\n        return True\n",
        encoding="utf-8",
    )
    return proj


def test_handshake_and_notifications(mcp_server: MCPServer):
    """Asserts JSON-RPC 2.0 handshake compliance with MCP protocol version '2024-11-05'."""
    init_req = {
        "jsonrpc": "2.0",
        "id": "req-1",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"},
        },
    }
    init_resp = mcp_server.dispatch(init_req)
    assert init_resp is not None
    assert init_resp["jsonrpc"] == "2.0"
    assert init_resp["id"] == "req-1"

    result = init_resp["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert result["serverInfo"]["name"] == "context-firewall-mcp"
    assert result["serverInfo"]["version"] == "3.2.0"
    assert "tools" in result["capabilities"]

    # Notifications must be silently acknowledged with None (no JSON-RPC response)
    notify_req = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
    }
    assert mcp_server.dispatch(notify_req) is None


def test_tools_list_schema(mcp_server: MCPServer):
    """Asserts that tools/list exposes 'prune_file' and 'resolve_context_bundle' with valid schemas."""
    list_req = {
        "jsonrpc": "2.0",
        "id": "req-2",
        "method": "tools/list",
        "params": {},
    }
    resp = mcp_server.dispatch(list_req)
    assert resp is not None
    assert resp["id"] == "req-2"

    tools = resp["result"]["tools"]
    tool_map = {t["name"]: t for t in tools}

    assert "prune_file" in tool_map
    assert "resolve_context_bundle" in tool_map

    # Validate prune_file schema
    prune_schema = tool_map["prune_file"]["inputSchema"]
    assert prune_schema["type"] == "object"
    assert "path" in prune_schema["required"]
    assert "depth" in prune_schema["properties"]
    assert "strip_docs" in prune_schema["properties"]
    assert "language" in prune_schema["properties"]

    # Validate resolve_context_bundle schema
    bundle_schema = tool_map["resolve_context_bundle"]["inputSchema"]
    assert bundle_schema["type"] == "object"
    assert "target_file" in bundle_schema["required"]
    assert "project_root" in bundle_schema["properties"]


def test_tools_call_prune_file(mcp_server: MCPServer, tmp_path: Path):
    """Asserts that tools/call prune_file extracts interfaces and stubs without leaking bodies."""
    test_file = tmp_path / "order_service.py"
    test_file.write_text(
        """class OrderService:
    '''Core transaction orchestrator.'''
    def __init__(self, db_conn: str):
        self.conn = db_conn

    def process(self, order_id: str) -> bool:
        '''Processes payment and fulfillment.'''
        if not order_id:
            raise ValueError("Invalid order ID: confidential_order_token")
        internal_secret = 999 * 42
        return True
""",
        encoding="utf-8",
    )

    call_req = {
        "jsonrpc": "2.0",
        "id": "req-3",
        "method": "tools/call",
        "params": {
            "name": "prune_file",
            "arguments": {
                "path": str(test_file),
                "depth": "interface",
            },
        },
    }
    resp = mcp_server.dispatch(call_req)
    assert resp is not None
    assert resp["id"] == "req-3"

    res = resp["result"]
    assert res["isError"] is False
    assert len(res["content"]) == 1
    assert res["content"][0]["type"] == "text"

    pruned_text = res["content"][0]["text"]
    # Verify interface retention and body truncation
    assert "class OrderService:" in pruned_text
    assert "def process(self, order_id: str) -> bool:" in pruned_text
    assert "..." in pruned_text
    assert "raise ValueError('...')" in pruned_text
    assert "internal_secret" not in pruned_text
    assert "confidential_order_token" not in pruned_text


def test_tools_call_resolve_context_bundle(mcp_server: MCPServer, multi_module_project: Path):
    """Asserts that tools/call resolve_context_bundle produces multi-depth topological context."""
    target_file = multi_module_project / "app.py"

    call_req = {
        "jsonrpc": "2.0",
        "id": "req-4",
        "method": "tools/call",
        "params": {
            "name": "resolve_context_bundle",
            "arguments": {
                "target_file": str(target_file),
                "project_root": str(multi_module_project),
            },
        },
    }
    resp = mcp_server.dispatch(call_req)
    assert resp is not None
    assert resp["id"] == "req-4"

    res = resp["result"]
    assert res["isError"] is False
    bundle_text = res["content"][0]["text"]

    # Target file (D0) is preserved in full
    assert "### File: app.py [FULL]" in bundle_text
    assert "def start():" in bundle_text

    # Dependency file (D1) is interface-pruned
    assert "### File: worker.py [INTERFACE]" in bundle_text
    assert "secret_key_12345" not in bundle_text


def test_cache_hit_performance(mcp_server: MCPServer, tmp_path: Path):
    """Asserts that second invocation hits the warm cache and returns identical results."""
    test_file = tmp_path / "cached_module.py"
    test_file.write_text(
        "def compute(a: int, b: int) -> int:\n    '''Performs complex calculation.'''\n    res = a + b\n    return res\n",
        encoding="utf-8",
    )

    call_req = {
        "jsonrpc": "2.0",
        "id": "req-c1",
        "method": "tools/call",
        "params": {
            "name": "prune_file",
            "arguments": {"path": str(test_file)},
        },
    }
    resp1 = mcp_server.dispatch(call_req)
    resp2 = mcp_server.dispatch(call_req)

    assert resp1["result"]["content"][0]["text"] == resp2["result"]["content"][0]["text"]
    assert resp1["result"]["isError"] is False
    assert resp2["result"]["isError"] is False


def test_graceful_error_handling_in_tools_call(mcp_server: MCPServer, tmp_path: Path):
    """Asserts that syntax errors, missing files, or bad args return isError=True without crashing."""
    # 1. Missing file
    resp_missing = mcp_server.dispatch({
        "jsonrpc": "2.0",
        "id": "err-1",
        "method": "tools/call",
        "params": {
            "name": "prune_file",
            "arguments": {"path": str(tmp_path / "non_existent.py")},
        },
    })
    assert resp_missing["result"]["isError"] is True
    assert "not found" in resp_missing["result"]["content"][0]["text"].lower()

    # 2. Syntax error in source file
    broken_file = tmp_path / "broken.py"
    broken_file.write_text("def broken_syntax(:\n", encoding="utf-8")
    resp_syntax = mcp_server.dispatch({
        "jsonrpc": "2.0",
        "id": "err-2",
        "method": "tools/call",
        "params": {
            "name": "prune_file",
            "arguments": {"path": str(broken_file)},
        },
    })
    assert resp_syntax["result"]["isError"] is True
    assert "error" in resp_syntax["result"]["content"][0]["text"].lower()

    # 3. Missing required arguments
    resp_no_args = mcp_server.dispatch({
        "jsonrpc": "2.0",
        "id": "err-3",
        "method": "tools/call",
        "params": {
            "name": "prune_file",
            "arguments": {},
        },
    })
    assert resp_no_args["result"]["isError"] is True
    assert "required" in resp_no_args["result"]["content"][0]["text"].lower()

    # 4. Unknown tool
    resp_unknown_tool = mcp_server.dispatch({
        "jsonrpc": "2.0",
        "id": "err-4",
        "method": "tools/call",
        "params": {
            "name": "non_existent_tool",
            "arguments": {},
        },
    })
    assert resp_unknown_tool["result"]["isError"] is True
    assert "unknown tool" in resp_unknown_tool["result"]["content"][0]["text"].lower()


def test_malformed_json_and_unknown_method(mcp_server: MCPServer):
    """Asserts JSON-RPC standard error codes: -32700 for parse error, -32601 for unknown method."""
    # 1. Parse error
    raw_bad_json = "NOT_VALID_JSON{}"
    res_str = mcp_server.process_raw_line(raw_bad_json)
    assert res_str is not None
    res_dict = json.loads(res_str)
    assert res_dict["error"]["code"] == -32700

    # 2. Non-object JSON
    raw_array_json = "[1, 2, 3]"
    res_array_str = mcp_server.process_raw_line(raw_array_json)
    assert res_array_str is not None
    res_array_dict = json.loads(res_array_str)
    assert res_array_dict["error"]["code"] == -32700

    # 3. Unknown method
    unknown_req = {
        "jsonrpc": "2.0",
        "id": "err-method",
        "method": "system/restart",
        "params": {},
    }
    resp = mcp_server.dispatch(unknown_req)
    assert resp is not None
    assert resp["error"]["code"] == -32601
    assert "Method not found" in resp["error"]["message"]


def test_stdio_loop_hygiene_and_content_length(mcp_server: MCPServer, monkeypatch):
    """Asserts strict stdio hygiene (valid JSON to stdout, diagnostic to stderr, Content-Length support)."""
    # Simulate a stream with:
    # 1. initialize request (line-delimited)
    # 2. ping request with Content-Length header
    # 3. an empty line
    payload_ping = json.dumps({"jsonrpc": "2.0", "id": 100, "method": "ping"})
    stream_content = (
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) + "\n\n"
        f"Content-Length: {len(payload_ping)}\r\n\r\n{payload_ping}\n"
    )

    mock_stdin = io.StringIO(stream_content)
    mock_stdout = io.StringIO()
    mock_stderr = io.StringIO()

    monkeypatch.setattr("sys.stdin", mock_stdin)
    monkeypatch.setattr("sys.stdout", mock_stdout)
    monkeypatch.setattr("sys.stderr", mock_stderr)

    mcp_server.run_stdio_loop()

    # Stderr received startup notice
    stderr_output = mock_stderr.getvalue()
    assert "context-firewall-mcp" in stderr_output
    assert "Server listening on stdio" in stderr_output

    # Stdout received purely valid JSON frames
    stdout_output = mock_stdout.getvalue().strip()
    lines = [line for line in stdout_output.split("\n") if line.strip()]
    assert len(lines) == 2

    frame1 = json.loads(lines[0])
    assert frame1["id"] == 1
    assert frame1["result"]["serverInfo"]["name"] == "context-firewall-mcp"

    frame2 = json.loads(lines[1])
    assert frame2["id"] == 100
    assert frame2["result"] == {}
