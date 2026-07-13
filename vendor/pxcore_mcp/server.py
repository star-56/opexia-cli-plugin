# pxcore_mcp/server.py — the MCP JSON-RPC handler, transport-agnostic.
#
# Implements the subset of MCP a tools server needs: initialize, tools/list, tools/call,
# and the initialized notification. One pure function, `handle(request) -> response|None`,
# so the same logic serves both stdio and HTTP. Stdlib only.
from __future__ import annotations

from typing import Any, Dict, Optional

from pxcore_mcp.tools import HANDLERS, TOOL_SPECS

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "pxcore", "version": "0.1.0"}


def _result(req_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle(request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Process one JSON-RPC message. Returns a response dict, or None for notifications
    (which get no reply, per JSON-RPC)."""
    method = request.get("method")
    req_id = request.get("id")
    params = request.get("params") or {}

    # notifications have no id and get no response.
    if req_id is None and isinstance(method, str) and method.startswith("notifications/"):
        return None

    if method == "initialize":
        # echo the client's protocol version when we can speak it; otherwise offer ours.
        client_ver = params.get("protocolVersion")
        return _result(req_id, {
            "protocolVersion": client_ver or PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
        })

    if method == "ping":
        return _result(req_id, {})

    if method == "tools/list":
        return _result(req_id, {"tools": TOOL_SPECS})

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        handler = HANDLERS.get(name)
        if handler is None:
            return _error(req_id, -32602, f"unknown tool: {name}")
        try:
            content = handler(args)
        except Exception as e:  # noqa: BLE001 — a tool error is a tool result, not a crash
            return _result(req_id, {
                "content": [{"type": "text", "text": f"{name} failed: {e}"}],
                "isError": True})
        return _result(req_id, {"content": content, "isError": False})

    if req_id is None:
        return None            # unknown notification — ignore
    return _error(req_id, -32601, f"method not found: {method}")
