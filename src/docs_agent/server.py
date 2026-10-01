"""MCP server: exposes official-documentation search as a tool.

Any MCP client (Gemini agent in agent.py, Gemini CLI, Claude Code, ...) can use it.
Run: python -m docs_agent.server   (stdio transport)
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from .backends import get_backend

mcp = MCPServer(
    name="official-docs",
    instructions=(
        "Search official upstream documentation (Kubernetes, vLLM, nftables, ...). "
        "Answers must be grounded in the returned passages and cite their URLs."
    ),
)
backend = get_backend()


@mcp.tool()
def search_official_docs(query: str, max_results: int = 5) -> dict:
    """Search official upstream documentation and return passages with source URLs.

    Args:
        query: A focused technical question or keywords, in English.
        max_results: Number of passages to return (1-10).
    """
    max_results = max(1, min(int(max_results), 10))
    results = backend.search(query, max_results)
    return {"query": query, "found": bool(results), "results": results}


def main():
    mcp.run("stdio")


if __name__ == "__main__":
    main()
