"""
src/ctxfw/mcp.py — Model Context Protocol (MCP) Server over stdio (v3.4.0)
Exposes deterministic context pruning and topological bundle resolution
to AI agents (Cursor, Claude Code, Windsurf) using JSON-RPC 2.0.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Dict, Optional

from ctxfw.core.contracts import (
    OptimizationRequestDTO,
    OptimizationResultDTO,
    PruningDepth,
    SupportedLanguage,
)
from ctxfw.core.pruner import DeterministicContextPruner
from ctxfw.core.topological import ContextFirewallEngine
from ctxfw.storage.cache import LocalSemanticCache
from ctxfw import __version__


class MCPServer:
    """Model Context Protocol server implementing JSON-RPC 2.0 over stdio."""

    PROTOCOL_VERSION = "2024-11-05"
    SERVER_NAME = "context-firewall-mcp"
    SERVER_VERSION = f"{__version__}"

    def __init__(self, cache: Optional[LocalSemanticCache] = None):
        self.running = True
        self.cache = cache or LocalSemanticCache()

    def handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handles MCP protocol handshake."""
        return {
            "protocolVersion": self.PROTOCOL_VERSION,
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": self.SERVER_NAME,
                "version": f"{__version__}",
            },
        }

    def handle_tools_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Lists available context compacting tools."""
        tool_annotations = {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        }

        return {
            "tools": [
                {
                    "name": "prune_file",
                    "description": (
                        "Extract semantic interfaces, types, pydantic models, sanitized raises, and signatures "
                        "from a source file while replacing procedural bodies with AST stubs. Use this when you "
                        "only need to inspect contracts or APIs of an individual dependency without ingesting "
                        "raw implementation code. Does not modify files on disk (pure in-memory AST operation)."
                    ),
                    "annotations": tool_annotations,
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Absolute or relative path to the source file",
                            },
                            "depth": {
                                "type": "string",
                                "description": "Pruning depth: 'full', 'interface', or 'nominal'",
                                "default": "interface",
                            },
                            "strip_docs": {
                                "type": "boolean",
                                "description": "Whether to strip docstrings entirely",
                                "default": False,
                            },
                            "language": {
                                "type": "string",
                                "description": "Programming language (python, typescript, javascript, go, java)",
                                "default": "python",
                            },
                        },
                        "required": ["path"],
                    },
                    "outputSchema": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "array",
                                "description": "Semantic interface stubs extracted via in-memory Tree-Sitter AST",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {"type": "string", "enum": ["text"]},
                                        "text": {"type": "string", "description": "Pruned source code with AST stubs"},
                                    },
                                    "required": ["type", "text"],
                                },
                            },
                            "isError": {
                                "type": "boolean",
                                "description": "True if pruning encountered a fatal parsing or file resolution failure",
                            },
                        },
                        "required": ["content", "isError"],
                    },
                },
                {
                    "name": "resolve_context_bundle",
                    "description": (
                        "Calculate topological dependency graph distances (D0 full target, D1 interface stubs, "
                        "D2 nominal symbols) for an active target file and compile a token-pruned Markdown context bundle. "
                        "Use this as your primary context builder before editing a file in a multi-module project. "
                        "For inspecting isolated files, use prune_file instead. Read-only operation."
                    ),
                    "annotations": tool_annotations,
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "target_file": {
                                "type": "string",
                                "description": "Path to the active target file in editing (D0)",
                            },
                            "project_root": {
                                "type": "string",
                                "description": "Root directory of the project. Defaults to target file's directory.",
                            },
                        },
                        "required": ["target_file"],
                    },
                    "outputSchema": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "array",
                                "description": "Compiled topological Markdown prompt context bundle",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {"type": "string", "enum": ["text"]},
                                        "text": {"type": "string", "description": "Token-optimized Markdown context bundle"},
                                    },
                                    "required": ["type", "text"],
                                },
                            },
                            "isError": {
                                "type": "boolean",
                                "description": "True if dependency resolution or file traversal failed",
                            },
                        },
                        "required": ["content", "isError"],
                    },
                },
                {
                    "name": "evaluate_spec_axioms",
                    "description": (
                        "Evaluate an architectural brief against formal determinism rules, negative invariant floors, "
                        "and the Axiom Completeness Index (ACI 1.0000). Use this during intake or planning phases "
                        "before writing code. Pure analytical evaluation with no side effects."
                    ),
                    "annotations": tool_annotations,
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "brief_text": {
                                "type": "string",
                                "description": "Markdown content of the architectural intake brief to evaluate",
                            },
                        },
                        "required": ["brief_text"],
                    },
                    "outputSchema": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "array",
                                "description": "JSON-serialized architectural determinism verification report",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {"type": "string", "enum": ["text"]},
                                        "text": {
                                            "type": "string",
                                            "description": "JSON report containing aci_score, negative_invariants_count, extracted_never_clauses, status, remediation_notes, and manifest_hash",
                                        },
                                    },
                                    "required": ["type", "text"],
                                },
                            },
                            "isError": {
                                "type": "boolean",
                                "description": "True if brief specification evaluation encountered an unhandled error",
                            },
                        },
                        "required": ["content", "isError"],
                    },
                },
            ]
        }

    def handle_tools_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatches tool execution with graceful error shielding."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        try:
            if tool_name == "prune_file":
                file_path_str = arguments.get("path")
                if not file_path_str:
                    return {
                        "content": [{"type": "text", "text": "Parameter 'path' is required."}],
                        "isError": True,
                    }

                file_path = Path(file_path_str).resolve()
                if not file_path.is_file():
                    return {
                        "content": [{"type": "text", "text": f"File not found: {file_path}"}],
                        "isError": True,
                    }

                code = file_path.read_text(encoding="utf-8")
                depth_val = arguments.get("depth", "interface").lower()
                depth_enum = PruningDepth(depth_val) if depth_val in PruningDepth._value2member_map_ else PruningDepth.INTERFACE
                strip_docs = bool(arguments.get("strip_docs", False))
                lang_val = arguments.get("language", "python").lower()
                lang_enum = SupportedLanguage(lang_val) if lang_val in SupportedLanguage._value2member_map_ else SupportedLanguage.PYTHON

                cache_key = LocalSemanticCache.generate_key(
                    source_code=code,
                    rules_version=DeterministicContextPruner.RULES_VERSION,
                    strip_docs=strip_docs,
                    depth=depth_enum.value,
                    language=lang_enum.value,
                )
                cached = self.cache.get(cache_key)
                if cached is not None:
                    return {
                        "content": [{"type": "text", "text": cached.pruned_code}],
                        "isError": False,
                    }

                req = OptimizationRequestDTO(
                    source_code=code,
                    language=lang_enum,
                    strip_docs=strip_docs,
                    depth=depth_enum,
                    sanitize_raises=True,
                )
                pruned_code, orig_c, pruned_c, saved, pct, ms = DeterministicContextPruner.prune(req)
                dto = OptimizationResultDTO(
                    pruned_code=pruned_code,
                    original_chars=orig_c,
                    pruned_chars=pruned_c,
                    estimated_tokens_saved=saved,
                    savings_percentage=pct,
                    cache_hit=False,
                    execution_ms=ms,
                    depth=depth_enum,
                )
                self.cache.set(cache_key, dto)

                return {
                    "content": [{"type": "text", "text": pruned_code}],
                    "isError": False,
                }

            elif tool_name == "resolve_context_bundle":
                target_file_str = arguments.get("target_file")
                if not target_file_str:
                    return {
                        "content": [{"type": "text", "text": "Parameter 'target_file' is required."}],
                        "isError": True,
                    }

                target_file = Path(target_file_str).resolve()
                if not target_file.is_file():
                    return {
                        "content": [{"type": "text", "text": f"Target file not found: {target_file}"}],
                        "isError": True,
                    }

                project_root_str = arguments.get("project_root")
                if project_root_str:
                    project_root = Path(project_root_str).resolve()
                else:
                    project_root = target_file.parent.resolve()

                firewall = ContextFirewallEngine(project_root=project_root, cache=self.cache)
                bundle = firewall.build_context(target_file)

                return {
                    "content": [{"type": "text", "text": bundle.to_prompt()}],
                    "isError": False,
                }

            elif tool_name == "evaluate_spec_axioms":
                brief_text = arguments.get("brief_text")
                if brief_text is None:
                    return {
                        "content": [{"type": "text", "text": "Parameter 'brief_text' is required."}],
                        "isError": True,
                    }

                from ctxfw.sieve.engine import evaluate_specification

                res = evaluate_specification(str(brief_text))
                payload = {
                    "aci_score": res.aci_score,
                    "negative_invariants_count": res.negative_invariants_count,
                    "extracted_never_clauses": res.extracted_never_clauses,
                    "status": res.status,
                    "remediation_notes": res.remediation_notes,
                    "manifest_hash": res.manifest_hash,
                }
                return {
                    "content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
                    "isError": False,
                }

            else:
                return {
                    "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
                    "isError": True,
                }

        except Exception as exc:
            return {
                "content": [{"type": "text", "text": f"Tool execution error: {str(exc)}"}],
                "isError": True,
            }

    def dispatch(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Processes a single JSON-RPC 2.0 request."""
        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        # Notifications (no id) do not produce responses
        if method == "notifications/initialized":
            return None

        if method == "initialize":
            result = self.handle_initialize(params)
            return {"jsonrpc": "2.0", "id": req_id, "result": result}

        elif method == "tools/list":
            result = self.handle_tools_list(params)
            return {"jsonrpc": "2.0", "id": req_id, "result": result}

        elif method == "tools/call":
            result = self.handle_tools_call(params)
            return {"jsonrpc": "2.0", "id": req_id, "result": result}

        elif method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        else:
            if req_id is not None:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}",
                    },
                }
            return None

    def process_raw_line(self, raw_line: str) -> Optional[str]:
        """Parses and dispatches a single raw line string from stdin."""
        line = raw_line.strip()
        if not line:
            return None

        try:
            req = json.loads(line)
            if not isinstance(req, dict):
                raise ValueError("JSON-RPC request must be a JSON object.")
        except Exception as err:
            error_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": f"Parse error: {str(err)}",
                },
            }
            return json.dumps(error_resp)

        resp = self.dispatch(req)
        if resp is not None:
            return json.dumps(resp)
        return None

    def run_stdio_loop(self):
        """Runs continuous JSON-RPC loop over sys.stdin and sys.stdout."""
        print(f"[{self.SERVER_NAME}] Server listening on stdio (MCP v{self.PROTOCOL_VERSION})", file=sys.stderr, flush=True)

        while self.running:
            line = sys.stdin.readline()
            if not line:
                break

            line_stripped = line.strip()
            if not line_stripped:
                continue

            # Support Content-Length framing (LSP / JSON-RPC framing)
            if line_stripped.lower().startswith("content-length:"):
                try:
                    content_length = int(line_stripped.split(":", 1)[1].strip())
                    while True:
                        header = sys.stdin.readline()
                        if not header or header.strip() == "":
                            break
                    body = sys.stdin.read(content_length)
                    output = self.process_raw_line(body)
                except Exception as e:
                    sys.stderr.write(f"Framing error: {e}\n")
                    sys.stderr.flush()
                    continue
            else:
                # Standard line-delimited JSON-RPC
                output = self.process_raw_line(line)

            if output:
                sys.stdout.write(output + "\n")
                sys.stdout.flush()


def main():
    server = MCPServer()
    server.run_stdio_loop()


if __name__ == "__main__":
    main()
