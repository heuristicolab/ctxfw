"""
proxy_gateway.py — Perimeter Reverse Proxy Gateway (v3.3.0)
Transparent HTTP reverse proxy implementing the Fail-Open Context Firewall policy
for OpenAI (/v1/chat/completions) and Anthropic (/v1/messages) protocols.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, Header, Request, Response
from fastapi.responses import JSONResponse
import httpx
import uvicorn

from contracts import (
    DeterministicContextPruner,
    LocalSemanticCache,
    OptimizationRequestDTO,
    OptimizationResultDTO,
    PruningDepth,
)
from polyglot_pruner import SupportedLanguage


app = FastAPI(
    title="Context Firewall Reverse Proxy Gateway",
    version="3.3.0",
    description="Transparent perimeter reverse proxy compacting LLM code contexts with sub-5ms latency and fail-open guarantees.",
)

# Supported language mappings
LANG_MAP: Dict[str, SupportedLanguage] = {
    "python": SupportedLanguage.PYTHON,
    "py": SupportedLanguage.PYTHON,
    "typescript": SupportedLanguage.TYPESCRIPT,
    "ts": SupportedLanguage.TYPESCRIPT,
    "javascript": SupportedLanguage.TYPESCRIPT,
    "js": SupportedLanguage.TYPESCRIPT,
    "go": SupportedLanguage.GO,
    "golang": SupportedLanguage.GO,
    "java": SupportedLanguage.JAVA,
}

# Regex to detect tagged file blocks:
# ### File: <filename> [Optional Depth]
# ```<lang>
# <code>
# ```
TAGGED_FILE_PATTERN = re.compile(
    r"(###\s+File:\s*(?P<filename>[^\n\[\r]+)(?:\[(?P<depth>[^\]]+)\])?\s*[\r\n]+```(?P<lang>[a-zA-Z0-9_\-\+]*)\s*[\r\n]+(?P<code>[\s\S]*?)[\r\n]+```)",
    re.MULTILINE,
)

# Regex to detect standard markdown code blocks:
# ```<lang>
# <code>
# ```
GENERIC_CODE_BLOCK_PATTERN = re.compile(
    r"(```(?P<lang>[a-zA-Z0-9_\-\+]+)\s*[\r\n]+(?P<code>[\s\S]*?)[\r\n]+```)",
    re.MULTILINE,
)

# Default upstream URLs
DEFAULT_OPENAI_UPSTREAM = "https://api.openai.com"
DEFAULT_ANTHROPIC_UPSTREAM = "https://api.anthropic.com"


def get_cache(custom_app: Optional[FastAPI] = None) -> LocalSemanticCache:
    target_app = custom_app or app
    if not hasattr(target_app.state, "cache") or target_app.state.cache is None:
        target_app.state.cache = LocalSemanticCache()
    return target_app.state.cache


def compact_code_snippet(
    code: str,
    lang_str: str,
    depth: PruningDepth = PruningDepth.INTERFACE,
    cache: Optional[LocalSemanticCache] = None,
) -> Tuple[str, int]:
    """
    Compacts a code snippet using DeterministicContextPruner and LocalSemanticCache.
    Returns (compacted_code, tokens_saved).
    Adheres strictly to Fail-Open invariant: on any syntax/parsing error, returns original code.
    """
    normalized_lang = lang_str.strip().lower()
    if normalized_lang not in LANG_MAP:
        return code, 0

    language = LANG_MAP[normalized_lang]

    try:
        # Check cache if available
        if cache is not None:
            cache_key = LocalSemanticCache.generate_key(
                source_code=code,
                rules_version=DeterministicContextPruner.RULES_VERSION,
                strip_docs=False,
                depth=depth.value,
                language=language.value,
            )
            cached = cache.get(cache_key)
            if cached is not None:
                return cached.pruned_code, cached.estimated_tokens_saved

        req = OptimizationRequestDTO(
            source_code=code,
            language=language,
            strip_docs=False,
            depth=depth,
            sanitize_raises=True,
        )
        pruned_code, orig_c, pruned_c, saved, pct, ms = DeterministicContextPruner.prune(req)

        # Store in cache if savings produced
        if cache is not None and saved > 0:
            dto = OptimizationResultDTO(
                pruned_code=pruned_code,
                original_chars=orig_c,
                pruned_chars=pruned_c,
                estimated_tokens_saved=saved,
                savings_percentage=pct,
                cache_hit=False,
                execution_ms=ms,
                depth=depth,
            )
            cache.set(cache_key, dto)

        return pruned_code, saved
    except Exception:
        # Fail-open: Return original untouched code
        return code, 0


def compact_text_payload(
    text: str,
    cache: Optional[LocalSemanticCache] = None,
) -> Tuple[str, int]:
    """
    Scans text for tagged file blocks or markdown code fences, compacting code blocks.
    Returns (compacted_text, total_tokens_saved).
    """
    if not text or "```" not in text:
        return text, 0

    total_saved = 0
    modified_text = text

    # Phase 1: Tagged file blocks (e.g. ### File: utils.py [INTERFACE])
    tagged_matches = list(TAGGED_FILE_PATTERN.finditer(text))
    if tagged_matches:
        for match in reversed(tagged_matches):
            full_match_str = match.group(0)
            filename = match.group("filename").strip()
            depth_str = (match.group("depth") or "").strip().upper()
            lang = match.group("lang") or "python"
            code = match.group("code")

            # Target file (D0 / FULL) must remain untouched
            if "FULL" in depth_str or "D0" in depth_str:
                continue

            target_depth = PruningDepth.NOMINAL if ("NOMINAL" in depth_str or "D2" in depth_str) else PruningDepth.INTERFACE
            compacted_code, saved = compact_code_snippet(code, lang, depth=target_depth, cache=cache)

            if saved > 0:
                header_part = f"### File: {filename}" + (f" [{depth_str}]" if depth_str else "")
                replacement = f"{header_part}\n```{lang}\n{compacted_code}\n```"
                start, end = match.span()
                modified_text = modified_text[:start] + replacement + modified_text[end:]
                total_saved += saved

        return modified_text, total_saved

    # Phase 2: Generic markdown code blocks (```python ... ```)
    generic_matches = list(GENERIC_CODE_BLOCK_PATTERN.finditer(text))
    if generic_matches:
        for match in reversed(generic_matches):
            lang = match.group("lang")
            code = match.group("code")

            compacted_code, saved = compact_code_snippet(code, lang, depth=PruningDepth.INTERFACE, cache=cache)
            if saved > 0:
                replacement = f"```{lang}\n{compacted_code}\n```"
                start, end = match.span()
                modified_text = modified_text[:start] + replacement + modified_text[end:]
                total_saved += saved

    return modified_text, total_saved


def inspect_and_compact_payload(
    body: Dict[str, Any],
    cache: Optional[LocalSemanticCache] = None,
) -> Tuple[Dict[str, Any], int]:
    """
    Recursively inspects messages/content in an OpenAI or Anthropic payload,
    compacting code blocks while preserving schema structure.
    """
    total_tokens_saved = 0
    compacted_body = dict(body)

    # Process "messages" array (OpenAI and Anthropic)
    if "messages" in compacted_body and isinstance(compacted_body["messages"], list):
        new_messages = []
        for msg in compacted_body["messages"]:
            if not isinstance(msg, dict):
                new_messages.append(msg)
                continue

            new_msg = dict(msg)
            content = new_msg.get("content")

            if isinstance(content, str):
                new_content, saved = compact_text_payload(content, cache)
                new_msg["content"] = new_content
                total_tokens_saved += saved
            elif isinstance(content, list):
                # Anthropic or OpenAI multi-part content
                new_parts = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str):
                        new_part = dict(part)
                        new_text, saved = compact_text_payload(new_part["text"], cache)
                        new_part["text"] = new_text
                        new_parts.append(new_part)
                        total_tokens_saved += saved
                    else:
                        new_parts.append(part)
                new_msg["content"] = new_parts

            new_messages.append(new_msg)
        compacted_body["messages"] = new_messages

    # Process Anthropic "system" field (string or list)
    if "system" in compacted_body:
        system_val = compacted_body["system"]
        if isinstance(system_val, str):
            new_sys, saved = compact_text_payload(system_val, cache)
            compacted_body["system"] = new_sys
            total_tokens_saved += saved
        elif isinstance(system_val, list):
            new_sys_list = []
            for item in system_val:
                if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                    new_item = dict(item)
                    new_text, saved = compact_text_payload(new_item["text"], cache)
                    new_item["text"] = new_text
                    new_sys_list.append(new_item)
                    total_tokens_saved += saved
                else:
                    new_sys_list.append(item)
            compacted_body["system"] = new_sys_list

    return compacted_body, total_tokens_saved


async def forward_upstream(
    request: Request,
    url: str,
    payload: Dict[str, Any],
    custom_client: Optional[httpx.AsyncClient] = None,
) -> Response:
    """Forwards modified request downstream to upstream LLM API."""
    client = custom_client or getattr(request.app.state, "upstream_client", None)
    should_close_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=60.0)
        should_close_client = True

    # Filter out hop-by-hop headers
    forward_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in {"host", "content-length", "x-context-firewall-bypass"}
    }

    try:
        upstream_resp = await client.post(
            url,
            json=payload,
            headers=forward_headers,
        )
        return Response(
            content=upstream_resp.content,
            status_code=upstream_resp.status_code,
            headers=dict(upstream_resp.headers),
            media_type=upstream_resp.headers.get("content-type", "application/json"),
        )
    except Exception as exc:
        return JSONResponse(
            status_code=502,
            content={"error": f"Bad Gateway: Upstream communication error: {str(exc)}"},
        )
    finally:
        if should_close_client:
            await client.aclose()


@app.get("/health")
def health_check():
    """Health check endpoint exposing cache statistics and fail-open policy status."""
    cache = get_cache(app)
    cache_entries = 0
    try:
        with cache._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM tokens_cache;")
            cache_entries = cur.fetchone()[0]
    except Exception:
        pass

    return {
        "status": "healthy",
        "version": "3.3.0",
        "service": "context-firewall-proxy",
        "fail_open_policy": True,
        "cache_entries": cache_entries,
    }


@app.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    x_context_firewall_bypass: Optional[str] = Header(None, alias="X-Context-Firewall-Bypass"),
):
    """OpenAI-compatible chat completions proxy endpoint."""
    t0 = time.perf_counter()
    raw_body = await request.json()

    bypass = x_context_firewall_bypass is not None and x_context_firewall_bypass.lower() in {"true", "1"}
    cache = get_cache(request.app)

    if bypass:
        payload = raw_body
        tokens_saved = 0
        status_tag = "bypassed"
    else:
        try:
            payload, tokens_saved = inspect_and_compact_payload(raw_body, cache)
            status_tag = "compacted" if tokens_saved > 0 else "pass-through"
        except Exception:
            # Fail-open: pass payload unmodified
            payload = raw_body
            tokens_saved = 0
            status_tag = "fail-open"

    latency_ms = (time.perf_counter() - t0) * 1000

    upstream_base = os.environ.get("UPSTREAM_BASE_URL", DEFAULT_OPENAI_UPSTREAM)
    upstream_url = f"{upstream_base.rstrip('/')}/v1/chat/completions"

    resp = await forward_upstream(request, upstream_url, payload)
    resp.headers["X-Tokens-Saved"] = str(tokens_saved)
    resp.headers["X-Firewall-Latency-Ms"] = f"{latency_ms:.3f}"
    resp.headers["X-Firewall-Status"] = status_tag
    return resp


@app.post("/v1/messages")
async def messages_completion(
    request: Request,
    x_context_firewall_bypass: Optional[str] = Header(None, alias="X-Context-Firewall-Bypass"),
):
    """Anthropic-compatible messages proxy endpoint."""
    t0 = time.perf_counter()
    raw_body = await request.json()

    bypass = x_context_firewall_bypass is not None and x_context_firewall_bypass.lower() in {"true", "1"}
    cache = get_cache(request.app)

    if bypass:
        payload = raw_body
        tokens_saved = 0
        status_tag = "bypassed"
    else:
        try:
            payload, tokens_saved = inspect_and_compact_payload(raw_body, cache)
            status_tag = "compacted" if tokens_saved > 0 else "pass-through"
        except Exception:
            # Fail-open
            payload = raw_body
            tokens_saved = 0
            status_tag = "fail-open"

    latency_ms = (time.perf_counter() - t0) * 1000

    upstream_base = os.environ.get("ANTHROPIC_UPSTREAM_BASE_URL") or os.environ.get("UPSTREAM_BASE_URL") or DEFAULT_ANTHROPIC_UPSTREAM
    upstream_url = f"{upstream_base.rstrip('/')}/v1/messages"

    resp = await forward_upstream(request, upstream_url, payload)
    resp.headers["X-Tokens-Saved"] = str(tokens_saved)
    resp.headers["X-Firewall-Latency-Ms"] = f"{latency_ms:.3f}"
    resp.headers["X-Firewall-Status"] = status_tag
    return resp


def main():
    parser = argparse.ArgumentParser(description="Context Firewall Reverse Proxy Gateway (v3.3.0)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host address to bind")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
    parser.add_argument("--upstream", type=str, default=None, help="Upstream base URL")
    args = parser.parse_args()

    if args.upstream:
        os.environ["UPSTREAM_BASE_URL"] = args.upstream

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
