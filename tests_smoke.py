"""Smoke test: start the MCP server over stdio, list tools, call the search tool."""
import asyncio, json, os, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main(q):
    p = StdioServerParameters(command=sys.executable, args=["-m", "docs_agent.server"], env={**os.environ})
    async with stdio_client(p) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        print("tools:", [t.name for t in (await s.list_tools()).tools])
        res = await s.call_tool("search_official_docs", {"query": q, "max_results": 3})
        data = res.structured_content or json.loads(res.content[0].text)
        print("found:", data["found"])
        for x in data["results"]:
            print(" -", x["project"], "|", x["url"], "|", x["snippet"][:90].replace("\n", " "))

asyncio.run(main(" ".join(sys.argv[1:]) or "How do I drain a Kubernetes node safely?"))
