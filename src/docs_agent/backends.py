"""Search backends for official documentation.

Every backend returns the same shape so the MCP tool and the agent never care
where the passages came from:

    [{"title": str, "url": str, "project": str, "snippet": str}, ...]

Backends:
  demo    bundled sample corpus, keyword scoring, no cloud account needed
  vertex  Vertex AI Search (Discovery Engine) engine over your own doc corpus
  ssh     any remote command that prints `ask --json`-style output
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


STOPWORDS = {"how", "the", "and", "for", "what", "can", "with", "does", "use", "you", "your", "from", "safely", "configure"}


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9][a-z0-9_.-]+", text.lower()) if len(t) > 2 and t not in STOPWORDS}


class DemoBackend:
    """Keyword search over sample_docs/*.json. Good enough to show the flow."""

    def __init__(self, path: Path | None = None):
        path = path or ROOT / "sample_docs"
        self.docs = []
        for f in sorted(path.glob("*.json")):
            self.docs.extend(json.loads(f.read_text(encoding="utf-8")))

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        q = _tokens(query)
        scored = []
        for d in self.docs:
            body = _tokens(d["title"] + " " + d["text"] + " " + " ".join(d.get("keywords", [])))
            score = len(q & body)
            if score:
                scored.append((score, d))
        scored.sort(key=lambda x: -x[0])
        return [
            {"title": d["title"], "url": d["url"], "project": d["project"], "snippet": d["text"]}
            for _, d in scored[:max_results]
        ]


class VertexSearchBackend:
    """Vertex AI Search engine (Discovery Engine REST API, Application Default Credentials)."""

    def __init__(self):
        import google.auth
        from google.auth.transport.requests import AuthorizedSession

        self.project = os.environ["VERTEX_PROJECT"]
        self.engine = os.environ["VERTEX_ENGINE"]
        self.location = os.environ.get("VERTEX_LOCATION", "global")
        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        self.http = AuthorizedSession(creds)

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        host = "discoveryengine.googleapis.com"
        if self.location != "global":
            host = f"{self.location}-{host}"
        url = (
            f"https://{host}/v1/projects/{self.project}/locations/{self.location}"
            f"/collections/default_collection/engines/{self.engine}"
            "/servingConfigs/default_search:search"
        )
        body = {
            "query": query,
            "pageSize": max_results,
            "contentSearchSpec": {
                "snippetSpec": {"returnSnippet": True},
                "extractiveContentSpec": {"maxExtractiveSegmentCount": 1},
            },
        }
        r = self.http.post(url, json=body, timeout=30)
        r.raise_for_status()
        out = []
        for res in r.json().get("results", []):
            doc = res.get("document", {})
            sd, dd = doc.get("structData", {}), doc.get("derivedStructData", {})
            segs = dd.get("extractive_segments") or []
            snips = dd.get("snippets") or []
            text = segs[0].get("content", "") if segs else (snips[0].get("snippet", "") if snips else "")
            out.append({
                "title": dd.get("title") or sd.get("path") or doc.get("id", ""),
                "url": sd.get("url") or dd.get("link", ""),
                "project": sd.get("source", ""),
                "snippet": re.sub(r"<[^>]+>", "", text)[:1500],
            })
        return out


class SshBackend:
    """Delegates to a remote `ask --json` endpoint, e.g. a locked-down SSH account.

    DOCS_SSH_CMD is the command prefix, e.g. `ssh my-kb-host`; the remote side
    is expected to run `ask --json "<question>"` and print
    {"answered": bool, "answer": str, "citations": [{"title","uri","project"}]}.
    """

    def __init__(self):
        self.prefix = shlex.split(os.environ["DOCS_SSH_CMD"])

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        remote = "ask --json " + shlex.quote(query)
        p = subprocess.run(self.prefix + [remote], capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            raise RuntimeError(p.stderr.strip()[:500])
        data = json.loads(p.stdout)
        if not data.get("answered"):
            return []
        cites = data.get("citations", [])[:max_results]
        return [{
            "title": "Grounded summary from the knowledge base",
            "url": cites[0]["uri"] if cites else "",
            "project": cites[0].get("project", "") if cites else "",
            "snippet": data.get("answer", ""),
        }] + [
            {"title": c.get("title", ""), "url": c.get("uri", ""), "project": c.get("project", ""), "snippet": ""}
            for c in cites
        ]


def get_backend():
    name = os.environ.get("DOCS_BACKEND", "demo").lower()
    return {"demo": DemoBackend, "vertex": VertexSearchBackend, "ssh": SshBackend}[name]()
