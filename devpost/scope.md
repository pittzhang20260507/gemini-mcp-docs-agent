---
doc: scope
status: approved
---

> **About these planning docs.** `scope.md`, `prd.md` and `spec.md` were written with the Devpost Learn Skill Pack templates **after** the project was built (October 2026). They record the final design that shipped and how it got there. The original plan changed several times during the build; those changes are kept in the "Explicitly Cut" and "Decisions" sections instead of being rewritten as if they had been planned up front.

# Official-Docs Ops Agent

An evidence-check step for multi-AI engineering workflows: every AI agent is required to consult a knowledge base of official upstream docs (through MCP or a locked-down `ask` endpoint) before it finalizes a technical answer, and then decides for itself how to use what it found.

## The Unique Kernel
**Mandatory consult, AI-judged adoption.** The check is enforced on every agent (Claude Code, Codex, Grok, Gemini/AGY) by CLI-side rules, but the evidence is advisory: each agent weighs the official-doc passages against its own reasoning and the other agents' conclusions and decides what to adopt. It is one more verification step in a scientific, repeatable multi-AI loop, not a filter that overrides the agents.

## Who It's For
The first users are **AI agents**, not people: the coding agents in one operator's multi-AI workflow (plan → design → verify → implement → re-verify → implement). The human operator orchestrates them and approves production changes. Today, without this step, agents fall back on memory or web pages of unknown age and provenance.

## The Core Loop
An agent receives a technical task → (if it searched the web, or the rule otherwise applies) it is required to query the official-docs knowledge base → it gets grounded passages with commit-pinned GitHub links, or a clear "out of domain / not covered" → it marks each key claim as consistent / conflicting / not covered and decides what to trust → other agents repeat the same check during cross-verification. It repeats on every task, so the check becomes part of how the workflow works rather than an extra chore.

## Inspiration & Identity
Engineering discipline over cleverness: "stability over capability". Quiet, auditable, boring in a good way. Every check leaves a run ID in the log.

## Why This Matters to the Learner
Building toward FDE / AI-infrastructure work: a commercially compliant internal AI platform that coordinates mainstream AI tools and APIs, cost-effective and quick to deploy. This project uses free Google Cloud credits (GenAI App Builder) to give every agent the same grounded evidence source.

## What "Working" Looks Like
- The enforcement fires reliably in each agent's CLI, and the server log shows a real call per agent (`who=claude|grok|agy|...`), not the agent's self-report.
- An in-scope question returns a step-by-step grounded answer with commit-pinned citations in a few seconds.
- An out-of-scope question returns "out of domain" with no citations: no guessing.
- The "oh, that's cool" beat: an agent's final answer ends with a short evidence check, each claim tagged consistent / conflicting / not covered, with links.

## The POC Boundary
- Official-docs knowledge base: 30 upstream repos, nightly incremental sync into Vertex AI Search.
- One query path for all agents (restricted `ask` endpoint) plus an open-source MCP server + Gemini agent that anyone can run with a demo corpus.
- CLI-side rules/hooks that require the check for each agent in the operator's workflow.

## Later
- A shared rule patch for all agents: before tagging a claim "consistent", confirm the KB answer has no "does not contain / no information" caveat and the citation supports that specific claim, not just the topic.
- Broader "mainstream global docs" sources beyond the 30 official repos.

## Explicitly Cut
- **AI agents living on the server**: four resident AI accounts each needed their own identity, tokens and permissions; too fragile. Replaced by one restricted account that can only ask.
- **Google-managed remote MCP per identity**: per-identity IAM roles and 403 errors. Replaced by server-side grounded answers, with MCP offered on the client side.
- **Forcing answers to come only from official docs**: replaced by mandatory consult + AI-judged adoption, because the agents together are better judges than a hard filter.
- **Local model / Docker on the VM**: 2 vCPU / 6 GB with no GPU can't serve a useful model; Docker's iptables rules conflict with the hand-built nftables baseline.
