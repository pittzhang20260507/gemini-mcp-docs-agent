"""Gemini agent that answers ops questions only from official docs, via MCP.

    export GEMINI_API_KEY=...            # https://aistudio.google.com/apikey
    python -m docs_agent.agent "How do I drain a Kubernetes node safely?"

Or on Vertex AI: GOOGLE_GENAI_USE_VERTEXAI=true GOOGLE_CLOUD_PROJECT=... GOOGLE_CLOUD_LOCATION=us-central1
"""

from __future__ import annotations

import asyncio
import os
import sys

from google import genai
from google.genai import types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

SYSTEM = """You are an infrastructure operations assistant.
Rules:
1. Before answering, call search_official_docs (you may call it more than once with refined queries).
2. Answer ONLY from the returned passages. Do not use memory, blogs, or guesses.
3. Every factual step must cite a source URL in [n] form; list the URLs at the end under "Sources".
4. If the tool returns nothing relevant, say "Not found in the official docs I have access to." and stop.
5. Prefer exact commands, flags and config keys as written in the docs."""


async def ask(question: str) -> str:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "docs_agent.server"],
        env={**os.environ},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            client = genai.Client()
            resp = await client.aio.models.generate_content(
                model=MODEL,
                contents=question,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM,
                    temperature=0.1,
                    tools=[session],  # google-genai calls MCP tools automatically
                ),
            )
            return resp.text or ""


def main():
    question = " ".join(sys.argv[1:]) or "How do I drain a Kubernetes node safely?"
    print(asyncio.run(ask(question)))


if __name__ == "__main__":
    main()
