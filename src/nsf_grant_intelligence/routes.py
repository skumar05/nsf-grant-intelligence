"""HTTP-only routes: landing page, /health and /version.

These sit next to the /mcp endpoint when the server runs over streamable HTTP. /health
is what load balancers and container platforms probe, so keep it fast and dependency-free.
"""

from __future__ import annotations

import html

from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from . import __version__

LANDING_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>NSF Grant Intelligence MCP</title>
<style>
:root {{ --bg:#fff; --fg:#1a1a1a; --muted:#5f6368; --card:#f3f4f6; --accent:#0b6bcb; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#16181d; --fg:#ececec; --muted:#9aa0a6; --card:#23262d; --accent:#6cb0ff; }} }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:16px/1.55 system-ui,-apple-system,Segoe UI,Arial,sans-serif; }}
main {{ max-width:46rem; margin:0 auto; padding:2.5rem 1rem 4rem; }}
h1 {{ font-size:1.8rem; margin:0 0 .25rem; }} h2 {{ font-size:1.15rem; margin:2rem 0 .5rem; }}
p {{ margin:.4rem 0; }} .muted {{ color:var(--muted); }}
code,pre {{ font-family:ui-monospace,Menlo,Consolas,monospace; font-size:.92em; }}
pre {{ background:var(--card); padding:.8rem 1rem; border-radius:8px; overflow-x:auto; }}
ul {{ list-style:none; padding:0; margin:0; }} li {{ background:var(--card); border-radius:8px; padding:.6rem .9rem; margin:.4rem 0; }}
li code {{ color:var(--accent); font-weight:600; }} a {{ color:var(--accent); }}
</style></head><body><main>
<h1>NSF Grant Intelligence MCP</h1>
<p class="muted">An MCP server that lets an AI assistant search and analyze 500,000+ National Science Foundation
awards through the public NSF Award API. This is a server for MCP clients, not a website.</p>
<h2>Connect</h2>
<p>MCP endpoint (streamable HTTP): <code>{mcp_url}</code></p>
<pre>claude mcp add --transport http nsf-grant-intelligence {mcp_url}</pre>
<p class="muted">Health check: <a href="{health_url}">{health_url}</a>. This public demo has no authentication
and only reads public data.</p>
<h2>Tools ({n_tools})</h2>
<ul>
{tools}
</ul>
<h2>Try asking</h2>
<ul>
<li>Which NSF programs fund coral reef research since 2022?</li>
<li>How much NSF robotics funding has Carnegie Mellon won since 2021?</li>
<li>What did NSF fund in quantum sensing, and who are the top institutions?</li>
</ul>
</main></body></html>
"""


def _base_url(request: Request) -> str:
    """Public base URL, honoring the proxy headers a load balancer sets."""
    proto = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host.split(',')[0].strip()}"


def _summary(description: str | None) -> str:
    """First paragraph of a tool description, on one line (docstrings wrap mid-sentence)."""
    first = (description or "").strip().split("\n\n")[0]
    return " ".join(first.split())


def register_routes(mcp: MCPServer) -> None:
    @mcp.custom_route("/", methods=["GET"])
    async def landing(request: Request) -> HTMLResponse:
        """Human-friendly page for anyone who opens the server's URL in a browser."""
        base = _base_url(request)
        tools = await mcp.list_tools()
        items = "\n".join(
            f"<li><code>{html.escape(t.name)}</code><br>"
            f'<span class="muted">{html.escape(_summary(t.description))}</span></li>'
            for t in tools
        )
        return HTMLResponse(
            LANDING_PAGE.format(
                mcp_url=html.escape(f"{base}/mcp"),
                health_url=html.escape(f"{base}/health"),
                n_tools=len(tools),
                tools=items,
            )
        )

    @mcp.custom_route("/health", methods=["GET"])
    async def health(request: Request) -> JSONResponse:
        """Liveness probe for load balancers and container platforms (HTTP transport only)."""
        return JSONResponse({"status": "healthy", "service": "nsf-grant-intelligence"})

    @mcp.custom_route("/version", methods=["GET"])
    async def version(request: Request) -> JSONResponse:
        return JSONResponse({"version": __version__})
