# pxcore_mcp/__main__.py — `pxcore-mcp` entry point.
#
#   pxcore-mcp                 # stdio (default; local dev, coding CLIs)
#   pxcore-mcp --http[:port]   # HTTP (Next.js / serverless callers)
#
# The active model is read from PXCORE_MODEL (out-of-band, since MCP does not surface it).
from __future__ import annotations

import argparse
import os
import sys

from pxcore_mcp import transport


def main() -> None:
    ap = argparse.ArgumentParser(prog="pxcore-mcp",
                                 description="pxcore MCP server (imaged tool results).")
    ap.add_argument("--http", action="store_true", help="serve over HTTP instead of stdio")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()

    sys.stderr.write(f"pxcore: model={os.environ.get('PXCORE_MODEL', 'claude-fable-5')}\n")
    sys.stderr.flush()

    if a.http:
        transport.serve_http(a.host, a.port)
    else:
        transport.serve_stdio()


if __name__ == "__main__":
    main()
