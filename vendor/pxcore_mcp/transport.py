# pxcore_mcp/transport.py — stdio and HTTP transports for the MCP handler. Stdlib only.
#
# stdio: newline-delimited JSON-RPC on stdin/stdout — what Claude Code and local clients use.
# http:  a single JSON-RPC-over-POST endpoint — the (non-streaming) Streamable HTTP subset,
#        which the standard `@modelcontextprotocol/sdk` client and serverless callers (Next.js)
#        can POST to. Returns application/json.
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict

from pxcore_mcp.server import handle


def serve_stdio() -> None:
    """Read one JSON-RPC message per line, write one response per line. Robust to blank lines
    and parse errors (a malformed line gets a JSON-RPC parse error, never a crash)."""
    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            out.write(json.dumps({"jsonrpc": "2.0", "id": None,
                                  "error": {"code": -32700, "message": "parse error"}}) + "\n")
            out.flush()
            continue
        resp = handle(req)
        if resp is not None:
            out.write(json.dumps(resp) + "\n")
            out.flush()


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:
        pass  # quiet

    def _send(self, code: int, body: Dict[str, Any]) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b""
            req = json.loads(raw or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._send(400, {"jsonrpc": "2.0", "id": None,
                             "error": {"code": -32700, "message": "parse error"}})
            return
        resp = handle(req)
        if resp is None:
            self.send_response(202)      # accepted notification, no body
            self.end_headers()
            return
        self._send(200, resp)


def serve_http(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), _Handler)
    sys.stderr.write(f"pxcore MCP (http) on http://{host}:{port}\n")
    sys.stderr.flush()
    server.serve_forever()
