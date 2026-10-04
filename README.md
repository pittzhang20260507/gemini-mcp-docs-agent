# Official-Docs Ops Agent (Gemini + MCP + Vertex AI Search)

> An infrastructure-operations agent that **only answers from official upstream documentation** and cites the exact source for every step.
> Built on **Gemini**, the **Model Context Protocol (MCP)**, and **Vertex AI Search**.

▶️ **Demo video (2 min, English narration, EN/ZH subtitles):** https://youtu.be/l67ilza4aGk · [download MP4](media/demo.mp4) · subtitles: [EN](media/demo.en.srt) / [中文](media/demo.zh.srt) / [EN+中文](media/demo.en-zh.srt)

✍️ **Author's blog / 作者博客:** https://api-cloud.cc

## The problem

AI assistants are now part of day-to-day ops work (Kubernetes, nftables, fail2ban, vLLM, systemd...). Their most dangerous failure is not "I don't know"; it's a confident answer built from an outdated blog post or a half-remembered flag. On production firewalls and clusters, one wrong line can lock you out of a server.

## What this does

```
 Question ──> Gemini agent ──(MCP tools/call)──> search_official_docs
                 │                                     │
                 │                       ┌─────────────┼──────────────┐
                 │                     demo          vertex          ssh
                 │                 (bundled      (Vertex AI       (existing `ask`
                 │                  sample)       Search engine)   endpoint)
                 ▼
 Answer with [n] citations → official doc / GitHub source URLs
 or "Not found in the official docs I have access to."
```

- **MCP server** (`docs_agent.server`): exposes one tool, `search_official_docs(query, max_results)`. Any MCP client can use it: this Gemini agent, Gemini CLI, Claude Code, and others.
- **Gemini agent** (`docs_agent.agent`): `google-genai` with the MCP session passed straight in as a tool. A strict system prompt makes it search first, answer only from the passages, cite every step, and refuse when nothing relevant comes back.
- **Pluggable backends**:
  - `demo`: a small bundled corpus, so anyone can run it in 2 minutes with only a Gemini API key.
  - `vertex`: a Vertex AI Search engine over your own docs corpus. In production we index 30 upstream repos (8,530 documents).
  - `ssh`: calls an existing locked-down `ask --json` endpoint. This is how our production knowledge base is consumed today.

## Quick start

```bash
git clone <this repo> && cd gemini-mcp-docs-agent
python -m venv .venv && . .venv/bin/activate
pip install -e .
export GEMINI_API_KEY=...          # free key from https://aistudio.google.com/apikey
export DOCS_BACKEND=demo
docs-agent "How do I drain a Kubernetes node safely?"
docs-agent "How do I configure Redis Sentinel?"   # out of scope -> refuses instead of guessing
```

Test only the MCP server (no Gemini key needed):

```bash
DOCS_BACKEND=demo python tests_smoke.py "nftables set with CIDR ranges"
```

Use it from any MCP client (example `mcpServers` entry):

```json
{ "official-docs": { "command": "docs-mcp-server", "env": { "DOCS_BACKEND": "demo" } } }
```

Vertex AI Search backend:

```bash
gcloud auth application-default login
export DOCS_BACKEND=vertex VERTEX_PROJECT=your-project VERTEX_ENGINE=your-engine-id
```

## Development environment

| Layer | What we used |
|---|---|
| Workstation | Windows 11 laptop + WSL2 (Ubuntu, Python 3.12, `uv`) |
| Server | One small GCP Spot VM (2 vCPU / 6 GB, no GPU) in the Jakarta region, hardened with nftables + fail2ban + CrowdSec + PortSentry |
| Knowledge base | Vertex AI Search (Agent Search, Enterprise + LLM features) + Cloud Storage bucket, paid from GenAI App Builder credits |
| Corpus | 30 official upstream repos: AI platforms (vLLM, LiteLLM, Ollama, Open WebUI, Dify, LangGraph, KServe, Ray, HF Transformers, HF TGI, MCP spec), containers (Kubernetes, K3s, Docker), network/security (nftables, fail2ban, CrowdSec, PortSentry, Hysteria2, sing-box, CoreDNS, Caddy, nginx, acme.sh, Cloudflare), systems (systemd, Prometheus), languages (Python, Bash, Git) |
| Ops | Daily incremental sync via cron, Telegram alert after ≥2 consecutive failures, private GitHub repo for server code, per-run IDs in all logs |
| This demo | `mcp` 2.x Python SDK (`MCPServer`), `google-genai`, `gemini-2.5-flash` |

## AI collaborators

This project was built by one human operator working with several AI agents, each with a clear role and boundary:

| Who | Role |
|---|---|
| **Human operator** | Owns every decision: approved each production change, chose the architecture pivots, and set the "no AI acts without assignment" rule |
| **Claude Code** (WSL) | Main builder: server setup, sync pipeline, `ask` CLI, SSH gate, this MCP + Gemini demo, plus daily journal and rollback checkpoints |
| **Codex** | Independent **read-only reviewer**. Its acceptance review found 4 real issues (evidence-folder collisions under concurrency, partial-import handling, token-format validation, out-of-scope detection), all fixed |
| **Gemini / Grok** | Consumers: they query the knowledge base with their own restricted key instead of living on the server |

The point of this setup: **stability over capability**. An agent that drifts, guesses, or changes defaults on its own is not usable on shared infrastructure, even if it's smart. Grounding answers in official docs is the same idea applied to knowledge.

## How the design evolved and why

Full story in Chinese: [docs/JOURNEY.zh-CN.md](docs/JOURNEY.zh-CN.md). Summary:

| Initial plan | What we changed | Why |
|---|---|---|
| A shared "AI workbench" VM: 4 resident AI user accounts (Claude/Codex/Gemini/Grok), each with its own repo folder; Codex CLI installed on the server | **No AI lives on the server.** One restricted `kb` SSH account (`restrict` + forced-command gate) that can only run `ask`; the 4 AI users and the server-side Codex CLI were removed | Each resident AI needed its own Google identity, token refresh, file permissions and repo hooks. Every "it works" had to be re-proven per user, and one missed credential cost hours. The AIs already run, logged in, on the workstation; the server only has to answer questions |
| Google-managed remote MCP for Agent Search, called with each AI's credentials | A thin `ask` CLI on the server using Agent Search's own grounded answer generation; MCP is offered on the **client** side (this repo) | The remote MCP `tools/call` needed extra IAM roles per identity and failed with 403 errors that took a while to trace. Server-side generation is paid by Search credits and **uses no AI subscription quota**. Answers come back in 4–6 s |
| One test source (vLLM, 75 docs, random IDs) | 30 sources, 8,530 docs, **stable document IDs** = hash(source:path) with daily incremental sync (unchanged run takes 7 s) | Random IDs create duplicates on every re-import. Stable IDs let upstream edits overwrite in place and upstream deletions get removed |
| Long-lived service-account key | Root cron impersonates the SA every 30 min to mint a 1-hour token | The org policy forbids SA key creation, and short-lived tokens are safer anyway |
| Parallel imports | Fetch/upload stay parallel; imports are serialized per data store | A data store accepts only one import at a time (HTTP 409) |
| Trust `answered=true` | Add a grounding score; "found something" ≠ "covers the product you asked about" | A PostgreSQL replication question was "answered" with "no direct guide". The refusal path needs a confidence signal |
| Local model / Docker | Neither | 2 vCPU / 6 GB with no GPU can't serve a useful model; Docker's iptables rules conflict with the hand-built nftables baseline |

## Honest limitations

- The `demo` corpus is a handful of short paraphrased passages with links to the real docs, enough to show the flow but not a knowledge base.
- The model can still misread a correct passage. Citations make that checkable but don't prevent it.
- The `ssh` backend returns one grounded summary plus citations, not raw passages.

## Hackathon planning docs

Planning documents for Devpost *Build With AI: Basics*: [scope](devpost/scope.md) · [PRD](devpost/prd.md) · [spec](devpost/spec.md). They were written with the Devpost Learn Skill Pack templates after the build and record the final design and how it evolved.

## License

Apache-2.0

---

More write-ups on AI-native infrastructure operations: **https://api-cloud.cc**
