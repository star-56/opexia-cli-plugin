# pxcore_mcp — the developer MCP surface (sub-project 2).
#
# A spec-compliant MCP server that exposes pxcore's imaged-result tools. STDLIB ONLY: an MCP
# server receives JSON-RPC and returns content; it makes no outbound call, so it needs no
# HTTP client. Cross-language reach is delivered by MCP itself — a TypeScript / Next.js dev
# consumes it with the standard `@modelcontextprotocol/sdk`, no OpexIA package required.
#
# Two transports, same handler:
#   - stdio  (local dev, coding CLIs) — the default.
#   - http   (Next.js / serverless callers that cannot spawn a stdio subprocess).
#
# The active model id is supplied OUT OF BAND (env PXCORE_MODEL), because Claude Code / MCP
# do not tell a server which model is active. The server loads that model's profile and every
# imaging decision is made by the shared core.
__version__ = "0.1.0"
