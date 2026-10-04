---
doc: prd
status: approved
---

> Written after the build with the Devpost Learn Skill Pack template; see the note at the top of `scope.md`.

# Official-Docs Ops Agent — Product Requirements

## The Core Journey
1. An AI agent in the operator's workflow gets a technical task (for example, "how do I drain a Kubernetes node safely?").
2. If it used web search, or the task otherwise needs evidence, its CLI rule requires one knowledge-base query before it may finish its turn.
3. The query goes to the official-docs knowledge base through the agent's restricted access (or through the MCP tool `search_official_docs`).
4. The agent receives either grounded passages/answer with commit-pinned citations, or an explicit "out of domain / not covered".
5. The agent compares that evidence with its own reasoning, the web results and other agents' conclusions, and decides what to adopt.
6. Its answer ends with an evidence-check section: each key claim tagged **consistent**, **conflicting** (with which side it trusts and why) or **not covered**, plus the run ID.

## Screens and Layout
There is no GUI; the users are agents. The surfaces are:
- **CLI output** of the agent (Claude Code, Codex, Grok, Gemini/AGY), including the evidence-check section.
- **`ask --json` output**: `elapsed_s`, `answered`, `grounding_score`, `answer`, `citations[]`, `skipped_reasons[]`, `run_id`.
- **MCP tool result**: `{query, found, results[{source, url, text}]}`.
- **Server log** (`ask.log`): one line per query with `who=` and `run_id`, used by the operator to audit real usage.

## Look and Feel
Plain, terse, machine-readable first. JSON for tools; short tagged lists for agents' evidence checks. Every result traceable to a run ID and an upstream file.

## Features and Behavior

### Enforcement (per agent)
- Claude Code: a Stop hook blocks the turn if web search was used but no knowledge-base call with a `run_id` appeared; at most 3 blocks per turn, then it lets the turn end and logs a give-up (no infinite loop). A PostToolUse hook pushes the rule text after every web search.
- Other agents (Codex, Grok, Gemini/AGY): equivalent rules adapted to each CLI, each with its own restricted key and `who=` identity.
- Rule text lives in the hook/rule file for each agent, not in a shared instructions file, so one agent never picks up another agent's identity or key.

### Knowledge base
- 30 official upstream repos (AI platforms, containers, network/security, systems, languages), 8,530 documents.
- Answers include commit-pinned GitHub URLs.
- Out-of-scope questions return `answered: false` with `OUT_OF_DOMAIN_QUERY_IGNORED`.

### Open-source MCP server + Gemini agent
- One tool, `search_official_docs(query, max_results)`; works with any MCP client.
- Gemini agent: search first, answer only from passages, cite every step, refuse when nothing relevant comes back.
- Backends: `demo` (bundled sample, runs with just a Gemini key), `vertex` (your own engine), `ssh` (the restricted `ask` endpoint).

## States and Boundaries
- **Answered**: grounded answer + citations + grounding score.
- **Not covered / out of domain**: no answer, no citations; the agent must say "not covered", not guess.
- **"Answered" but weak**: a grounding score helps the agent tell "found something" from "covers this exact question".
- **KB unreachable**: the agent reports that the check could not run; the hook gives up after 3 blocks.

## Product Decisions
- The check is mandatory; adoption is the agent's call.
- Usage is verified from the server log (`who=`), never from an agent's self-report.
- Server-side answer generation is paid by Search credits, so checks use no AI subscription quota.

## What We're Building
The knowledge base, the restricted `ask` access, per-agent enforcement rules, and the open-source MCP server + Gemini agent with a demo corpus and a 2-minute demo video.

## Deferred From the POC
- Shared stricter "consistent" tagging rule for all agents (operator deferred).
- Additional mainstream sources beyond the 30 official repos.

## Possible Later Enhancements
- Usage dashboard from `ask.log` (calls per agent, answered rate).
- More backends for the MCP server.

## Non-Goals
- Replacing the agents' judgment with a hard "official docs only" filter.
- A human-facing chat app.
- Running models on the knowledge-base VM.

## Open Questions
- How often agents mark weakly related citations as "consistent" (seen with two agents on one test question); addressed by the deferred rule patch.
