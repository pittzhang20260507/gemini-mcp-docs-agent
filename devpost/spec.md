---
doc: spec
status: approved
---

> Written after the build with the Devpost Learn Skill Pack template; see the note at the top of `scope.md`.

# Official-Docs Ops Agent — Technical Spec

## How This Works, In Plain Language
Thirty official documentation repos are copied into Google's Vertex AI Search every night. Agents ask it questions through either a locked-down SSH command (`ask`) or an MCP tool. Each agent's CLI has a rule that won't let it finish a web-researched answer until it has asked the knowledge base once. The agent then decides what to believe.

## The Core Journey Through the System
```
agent CLI ──(rule/hook requires a check)──> ask --json "<question>"  or  MCP tools/call search_official_docs
                                                   │
                                     Vertex AI Search (grounded answer + citations)
                                                   │
agent <── answer / citations / grounding_score / run_id ──┘
  └─> evidence check in its reply (consistent / conflicting / not covered)
server ask.log: who=<agent> run_id=...   ← the operator audits this
```

## Stack
- Google Cloud: Vertex AI Search (Agent Search, Enterprise + LLM features), Cloud Storage, GenAI App Builder credits.
- One small GCP Spot VM (2 vCPU / 6 GB, no GPU), Jakarta region.
- Python 3.12; `mcp` 2.x Python SDK (`MCPServer`); `google-genai` with `gemini-2.5-flash`.
- Claude Code hooks (Python); equivalent rule files for Codex, Grok and Gemini/AGY CLIs.

## Where It Runs and How Someone Tries It
- Knowledge base and `ask`: on the VM; reachable only through a restricted SSH account.
- MCP server + Gemini agent: on the user's own machine. Anyone can try it:
  `pip install -e . && export GEMINI_API_KEY=... DOCS_BACKEND=demo && docs-agent "How do I drain a Kubernetes node safely?"`

## Look and Feel
JSON in, JSON out; agent replies end with a short tagged evidence list.

## Components

### Sync pipeline (server)
Fetch upstream repos → upload to Cloud Storage → import into Vertex AI Search. Fetch/upload run in parallel; imports are serialized per data store (one import at a time, avoids HTTP 409). Stable document IDs = hash(source:path), so edits overwrite in place and upstream deletions are removed. Unchanged nightly run: ~7 s. Telegram alert after ≥2 consecutive failures. Per-run IDs in every log.

### `ask` endpoint (server)
Restricted `kb` SSH account (`restrict` + forced-command gate) that can only run `ask`. Each agent has its own key and `who=` identity. Uses Vertex AI Search's grounded answer generation; returns answer, citations, grounding score, skipped reasons, run ID.

### Credentials (server)
No service-account keys (blocked by org policy). Root cron impersonates the service account every 30 min to mint a 1-hour token.

### Enforcement hooks (client)
Claude Code: PostToolUse on web search tools injects the rule; Stop hook blocks the turn until a KB call with a `run_id` is seen, max 3 blocks per turn, state per session, every decision logged. The hook only acts on Claude Code's own sessions so other tools that load it are not affected. Other agents: the same rule adapted to their CLIs.

### MCP server + Gemini agent (this repo)
`src/docs_agent/server.py` exposes `search_official_docs`; `agent.py` passes the MCP session to `google-genai` as a tool with a strict system prompt; `backends.py` implements `demo`, `vertex`, `ssh`.

## Data Model
- KB document: id = hash(source:path), source, path, commit-pinned URL, content.
- `ask` result: `elapsed_s`, `answered`, `grounding_score`, `answer`, `citations[{project, uri, title, excerpt}]`, `skipped_reasons[]`, `run_id`.
- MCP result: `{query, found, results[{source, url, text}]}`.

## File Structure
```
src/docs_agent/   server.py · agent.py · backends.py
sample_docs/      ops_docs.json (demo corpus)
media/            demo.mp4 + EN / ZH / EN-ZH subtitles
video/            build.py (slides → narration → MP4)
docs/             JOURNEY.zh-CN.md (design history)
devpost/          scope.md · prd.md · spec.md
```

## External Services and Dependencies
Vertex AI Search, Cloud Storage, Gemini API (AI Studio key for the demo), GitHub (upstream docs), Telegram (alerts).

## Important Failure Modes
- KB unreachable → agent states the check could not run; hook gives up after 3 blocks.
- Out-of-domain question → `answered: false`, no citations.
- "Answered" with weak coverage → grounding score; agents may still over-tag "consistent" (open issue).
- Import conflict (409) → prevented by serialized imports.

## What Was Simplified and Why
- One restricted account instead of resident AI users: simpler identity and audit.
- Server-side grounded generation instead of remote MCP per identity: fewer IAM roles, no AI quota used, 4–6 s answers.
- Demo corpus is a handful of paraphrased passages with links to the real docs: enough to show the flow without credentials.

## Decisions and Open Issues
- Decision: mandatory consult, AI-judged adoption.
- Decision: audit usage from the server log, not self-reports.
- Open: stricter shared "consistent" tagging rule (deferred by the operator).
