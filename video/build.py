"""Build the ~2-minute demo video: HTML slides -> PNG (Playwright) + narration (edge-tts) -> MP4 (ffmpeg).

Terminal scenes use real captured output from cap/*.txt (see README "Quick start").
Run: ../.venv/bin/python build.py   ->  out/demo.mp4
"""

import asyncio
import html
import json
import os
import subprocess
from pathlib import Path

import edge_tts
from playwright.async_api import async_playwright

HERE = Path(__file__).parent
OUT = HERE / "out"
VOICE = "en-US-AndrewNeural"
WATERMARK = "api-cloud.cc"  # blog URL, shown top-right for the whole video
TEMPO = 1.08  # speed narration up slightly to land near 2:00

CSS = """
*{box-sizing:border-box;margin:0}
body{width:1920px;height:1080px;background:#0b1020;color:#e8ecf5;font-family:'Noto Sans','DejaVu Sans',sans-serif;padding:50px 120px 230px;position:relative;overflow:hidden;display:flex;flex-direction:column;justify-content:center}
body:before{content:"";position:absolute;inset:0;background:radial-gradient(circle at 85% 10%,#1a3a8a55,transparent 50%),radial-gradient(circle at 5% 95%,#0f766e44,transparent 45%)}
.wrap{position:relative}
.kicker{font-size:28px;letter-spacing:4px;text-transform:uppercase;color:#7aa2ff;margin-bottom:24px}
h1{font-size:120px;line-height:1.05;font-weight:800}
h2{font-size:62px;font-weight:800;margin-bottom:44px}
.sub{font-size:40px;color:#aab4cc;margin-top:36px;line-height:1.4}
.pills{display:flex;gap:18px;margin-top:60px}
.pill{border:2px solid #3b5bdb;border-radius:999px;padding:12px 30px;font-size:30px;color:#c5d3ff}
ul{list-style:none;font-size:40px;line-height:1.55}
li{padding-left:44px;position:relative;margin-bottom:18px}
li:before{content:"";position:absolute;left:0;top:24px;width:16px;height:16px;border-radius:4px;background:#7aa2ff}
.warn li:before{background:#f59e0b}
b{color:#fff}
.term{background:#05070f;border:1px solid #26304a;border-radius:16px;padding:34px 40px;font-family:'DejaVu Sans Mono',monospace;font-size:var(--fs,24px);line-height:1.5;white-space:pre;color:#cfd8ea;box-shadow:0 30px 80px #0008}
.term .cmd{color:#7ee787}.term .ok{color:#79c0ff}.term .no{color:#ffa657}.term .dim{color:#7d8590}
.tag{position:absolute;top:-6px;right:0;font-size:24px;background:#0f766e;color:#d1fae5;padding:8px 20px;border-radius:8px}
.flow{display:flex;align-items:stretch;gap:22px;margin-top:20px}
.box{flex:1 1 0;background:#121a33;border:2px solid #2d3d6e;border-radius:18px;padding:28px;font-size:30px;line-height:1.35;min-height:250px}
.box h3{font-size:34px;color:#9ec1ff;margin-bottom:12px}
.arrow{font-size:56px;color:#7aa2ff;align-self:center}
table{border-collapse:collapse;font-size:31px;width:100%}
td,th{padding:16px 20px;border-bottom:1px solid #26304a;text-align:left;vertical-align:top}
th{color:#7aa2ff;font-size:26px;letter-spacing:2px;text-transform:uppercase}
td:first-child{color:#aab4cc;width:38%}
.foot{position:absolute;bottom:-30px;left:0;font-size:24px;color:#6b7690}
"""


def term(path, fs=24, tag="", width=999):
    out = []
    for line in (HERE / path).read_text().splitlines():
        if len(line) > width:
            line = line[: width - 1] + "…"
        e = html.escape(line)
        if line.startswith("$"):
            e = f'<span class="cmd">{e}</span>'
        elif "found: True" in line or '"answered": true' in line:
            e = f'<span class="ok">{e}</span>'
        elif "found: False" in line or '"answered": false' in line or "OUT_OF_DOMAIN" in line:
            e = f'<span class="no">{e}</span>'
        elif line.strip().startswith("[") or line.startswith(" - "):
            e = f'<span class="ok">{e}</span>'
        out.append(e)
    t = f'<span class="tag">{tag}</span>' if tag else ""
    return f'<div class="term" style="--fs:{fs}px;position:relative">{t}{chr(10).join(out)}</div>'


SCENES = [
    ("title",
     """<div class="kicker">Gemini · MCP · Vertex AI Search</div>
<h1>Official-Docs<br>Ops Agent</h1>
<div class="sub">An infrastructure assistant that answers <b>only</b> from official documentation,<br>and shows you the source for every step.</div>
<div class="pills"><span class="pill">Gemini 2.5 Flash</span><span class="pill">Model Context Protocol</span><span class="pill">Vertex AI Search</span></div>""",
     None),

    ("problem",
     """<div class="kicker">The problem</div><h2>Confident and wrong is worse than “I don't know”</h2>
<ul class="warn"><li>AI assistants are now part of everyday ops work</li>
<li>Answers built from <b>outdated blogs</b> or <b>half-remembered flags</b></li>
<li>On a production firewall, <b>one wrong line</b> can lock you out of the server</li></ul>""",
     None),

    ("arch",
     """<div class="kicker">Architecture</div><h2>Ground every answer in upstream docs</h2>
<div class="flow">
<div class="box"><h3>30 official repos</h3>Kubernetes, K3s, vLLM, nftables, fail2ban, CrowdSec, systemd, Prometheus, MCP spec…<br><br><b>Nightly incremental sync</b></div>
<div class="arrow">→</div>
<div class="box"><h3>Vertex AI Search</h3><b>8,530 documents</b><br>stable IDs, commit-pinned GitHub URLs</div>
<div class="arrow">→</div>
<div class="box"><h3>MCP server</h3><code>search_official_docs</code><br><br>any MCP client can use it</div>
<div class="arrow">→</div>
<div class="box"><h3>Gemini agent</h3>search first · answer only from passages · cite every step · refuse if nothing found</div>
</div>""",
     None),

    ("mcp",
     """<div class="kicker">Live · MCP server, demo backend</div><h2>A real MCP client calls the tool</h2>"""
     + term("cap/demo.txt", 22, "in scope", 118) + "<div style='height:30px'></div>" + term("cap/oos.txt", 22, "out of scope"),
     None),

    ("prod",
     """<div class="kicker">Live · production knowledge base</div>""" + term("cap/prod.txt", 17, "5.8 s · real output", 132),
     None),

    ("prod_oos",
     """<div class="kicker">Live · production knowledge base</div><h2>Out of domain? It says so.</h2>"""
     + term("cap/prod_oos.txt", 28, "real output"),
     None),

    ("journey",
     """<div class="kicker">How the design evolved</div>
<table><tr><th>We started with</th><th>We changed to, and why</th></tr>
<tr><td>4 AI agents living on the server, each with its own credentials</td><td><b>No AI on the server.</b> One locked-down SSH account that can only ask. Per-agent identities were fragile</td></tr>
<tr><td>Google-managed remote MCP, called per identity</td><td>Server-side grounded answers; <b>MCP on the client</b>. No AI subscription quota used</td></tr>
<tr><td>Long-lived service-account key</td><td><b>1-hour impersonated tokens</b>. Keys are blocked by org policy</td></tr>
<tr><td>Parallel imports, random doc IDs</td><td><b>Serialized imports, stable IDs</b>. Fixes 409 conflicts and duplicates</td></tr></table>""",
     None),

    ("team",
     """<div class="kicker">Built by one operator and a team of AI agents</div><h2>Stability over capability</h2>
<ul><li><b>Human operator</b>: approves every production change</li>
<li><b>Claude Code</b>: builder: pipeline, gate, MCP server, Gemini agent</li>
<li><b>Codex</b>: independent read-only reviewer, found 4 real bugs</li>
<li><b>Gemini &amp; Grok</b>: consumers, using restricted keys</li></ul>
<div class="sub">Open source · Apache-2.0 · <code>pip install -e . &amp;&amp; docs-agent "your question"</code></div>""",
     None),
]

# (English narration, Chinese subtitle) per sentence; English is spoken, both are shown.
NARRATION = {
    "title": [
        ("Official-Docs Ops Agent, built with Gemini, the Model Context Protocol, and Vertex AI Search.",
         "Official-Docs Ops Agent，基于 Gemini、模型上下文协议（MCP）和 Vertex AI Search 构建。"),
        ("It's an infrastructure assistant that answers only from official documentation, and shows you the source.",
         "这是一个基础设施运维助手：只依据官方文档回答，并给出每一条的出处。"),
    ],
    "problem": [
        ("AI assistants are now part of everyday infrastructure work.",
         "AI 助手已经成为日常基础设施运维的一部分。"),
        ("Their most dangerous failure isn't saying I don't know.",
         "它们最危险的失误，不是回答“我不知道”，"),
        ("It's a confident answer built on an outdated blog post, or a half-remembered flag.",
         "而是基于过时的博客或记错的参数，给出一个很自信的答案。"),
        ("On a production firewall, one wrong line can lock you out of the server.",
         "在生产防火墙上，一行配置写错，就可能把自己锁在服务器外面。"),
    ],
    "arch": [
        ("Thirty official upstream repositories, from Kubernetes and vLLM to nftables and systemd, sync every night into Vertex AI Search.",
         "30 个官方上游仓库，从 Kubernetes、vLLM 到 nftables、systemd，每晚同步进 Vertex AI Search。"),
        ("That's eight thousand five hundred documents, with stable IDs and commit-pinned links.",
         "共 8,530 篇文档，文档 ID 固定，链接锁定到具体提交。"),
        ("On top of that, an MCP server exposes one tool, search official docs.",
         "在此之上，MCP 服务提供一个工具：search_official_docs（检索官方文档）。"),
        ("A Gemini agent calls it, answers only from the returned passages, and cites every step.",
         "Gemini 智能体调用这个工具，只根据返回的原文作答，每一步都标注出处。"),
    ],
    "mcp": [
        ("Here's the MCP server on its own.",
         "先单独看 MCP 服务。"),
        ("A real MCP client lists the tool and calls it.",
         "一个真实的 MCP 客户端列出工具，并调用它。"),
        ("For the drain question, it returns the Kubernetes drain and disruption budget pages.",
         "问节点排空（drain），它返回 Kubernetes 的 drain 和 PodDisruptionBudget 文档。"),
        ("Redis Sentinel isn't in the sample corpus, so it returns nothing, and the agent refuses instead of guessing.",
         "Redis Sentinel 不在样例文档库里，所以返回为空，智能体会拒答，而不是瞎猜。"),
    ],
    "prod": [
        ("This is our production knowledge base.",
         "这是我们的生产知识库。"),
        ("One question, under six seconds.",
         "一个问题，不到 6 秒。"),
        ("You get a step-by-step answer generated from the docs, and every citation points to the exact file in the Kubernetes repository, pinned to a commit.",
         "得到基于文档生成的分步答案，每条引用都指向 Kubernetes 仓库里的具体文件，并锁定到某次提交。"),
    ],
    "prod_oos": [
        ("Ask about Oracle RAC, and it tells you plainly, out of domain, no answer, no citations.",
         "问 Oracle RAC，它会直接告诉你：超出范围，没有答案，也没有引用。"),
    ],
    "journey": [
        ("The design changed along the way.",
         "方案在过程中不断调整。"),
        ("We started with four AI agents living on the server, each with its own credentials.",
         "最初有 4 个 AI 智能体驻留在服务器上，各自持有凭据。"),
        ("Managing identities per agent was fragile, so now no AI lives on the server, only one locked-down account that can do nothing but ask.",
         "逐个管理身份太脆弱，所以现在服务器上不驻留任何 AI，只留一个受限账号，除了提问什么都做不了。"),
        ("We moved MCP to the client side, switched to short-lived tokens because long-lived keys are blocked, and serialized imports after hitting conflicts.",
         "MCP 移到客户端；长期密钥被策略禁止，改用短期令牌；导入撞上冲突后改为排队执行。"),
    ],
    "team": [
        ("Built by one human operator, with Claude Code as the builder.",
         "由一名运维负责人主导，Claude Code 负责建设。"),
        ("Codex reviewed it independently and found four real bugs, and Gemini and Grok use it as consumers.",
         "Codex 独立审查，发现了 4 个真实 bug；Gemini 和 Grok 作为使用方接入。"),
        ("Our rule is stability over capability.",
         "我们的原则：稳定优先于能力。"),
        ("It's open source under Apache 2.0.",
         "项目以 Apache 2.0 协议开源。"),
        ("Try it with your own question.",
         "用你自己的问题试试吧。"),
    ],
}


def dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(p)],
                       capture_output=True, text=True, check=True)
    return float(json.loads(r.stdout)["format"]["duration"])


async def main():
    OUT.mkdir(exist_ok=True)
    async with async_playwright() as pw:
        b = await pw.chromium.launch(executable_path=os.environ.get("CHROME") or None)
        pg = await b.new_page(viewport={"width": 1920, "height": 1080})
        for name, body, *_ in SCENES:
            await pg.set_content(f"<html><head><style>{CSS}</style></head><body><div class='wrap'>{body}</div></body></html>")
            await pg.screenshot(path=str(OUT / f"{name}.png"))
        await b.close()
    clips, total, subs = [], 0.0, []
    for name, *_ in SCENES:
        lines = NARRATION[name]
        mp3, bjson = OUT / f"{name}.mp3", OUT / f"{name}.bounds.json"
        await tts(" ".join(en for en, _ in lines), mp3, bjson, name)
        d = dur(mp3) / TEMPO + 0.9
        for (en, zh), (t0, t1) in zip(lines, align(lines, json.loads(bjson.read_text()))):
            subs.append((total + 0.4 + t0 / TEMPO, total + 0.4 + t1 / TEMPO, en, zh))
        total += d
        clip = OUT / f"{name}.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(OUT / f"{name}.png"),
                        "-i", str(mp3), "-af", f"atempo={TEMPO},adelay=400|400,apad", "-t", f"{d:.2f}",
                        "-vf", f"fade=in:st=0:d=0.3,fade=out:st={d - 0.35:.2f}:d=0.35,format=yuv420p",
                        "-r", "30", "-c:v", "libx264", "-tune", "stillimage", "-c:a", "aac", "-ar", "44100",
                        "-b:a", "160k", str(clip)], check=True)
        clips.append(clip)
        print(f"{name:10s} {d:5.1f}s")
    (OUT / "list.txt").write_text("".join(f"file '{c.name}'\n" for c in clips))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(OUT / "list.txt"),
                    "-c", "copy", str(OUT / "nosubs.mp4")], check=True)
    write_subs(subs, total)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(OUT / "nosubs.mp4"),
                    "-vf", f"ass={OUT / 'subs.ass'}", "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-c:a", "copy", "-movflags", "+faststart", str(OUT / "demo.mp4")], check=True)
    print(f"total {total:.1f}s, {len(subs)} subtitles -> {OUT / 'demo.mp4'}")


async def tts(text, mp3, bjson, name):
    """Synthesize narration and record sentence boundaries (cached; the service throttles)."""
    if mp3.exists() and bjson.exists():
        return
    for attempt in range(6):
        try:
            audio, bounds = bytearray(), []
            async for ch in edge_tts.Communicate(text, VOICE, rate="+4%", boundary="SentenceBoundary").stream():
                if ch["type"] == "audio":
                    audio += ch["data"]
                elif ch["type"] == "SentenceBoundary":
                    bounds.append({"start": ch["offset"] / 1e7, "end": (ch["offset"] + ch["duration"]) / 1e7,
                                   "text": ch["text"]})
            mp3.write_bytes(audio)
            bjson.write_text(json.dumps(bounds, indent=1))
            return
        except edge_tts.exceptions.NoAudioReceived:
            await asyncio.sleep(15 * (attempt + 1))
    raise RuntimeError(f"TTS failed for scene {name}")


def _norm(t):
    return "".join(c for c in t.lower() if c.isalnum())


def align(lines, bounds):
    """Map TTS sentence boundaries onto our sentences (TTS may split or merge differently)."""
    out, i = [], 0
    for en, _ in lines:
        target, acc, t0, t1 = _norm(en), "", None, None
        while i < len(bounds) and len(acc) < len(target):
            b = bounds[i]
            t0 = b["start"] if t0 is None else t0
            t1, acc = b["end"], acc + _norm(b["text"])
            i += 1
        if acc != target:
            raise RuntimeError(f"subtitle alignment failed: {en!r} vs {acc!r}")
        out.append((t0, t1))
    return out


def _ts(t, sep):
    h, m, sec = int(t // 3600), int(t % 3600 // 60), t % 60
    return f"{h}:{m:02d}:{sec:05.2f}" if sep == "." else f"{h:02d}:{m:02d}:{sec:06.3f}".replace(".", ",")


def write_subs(subs, total):
    ass = ["[Script Info]", "ScriptType: v4.00+", "PlayResX: 1920", "PlayResY: 1080", "WrapStyle: 0", "",
           "[V4+ Styles]",
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
           "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
           "MarginR, MarginV, Encoding",
           "Style: EN,Noto Sans,36,&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,0,0,0,0,100,100,0,0,1,2.5,0,2,140,140,96,1",
           "Style: ZH,Noto Sans CJK SC,38,&H0080E1FF,&H0080E1FF,&H00000000,&H90000000,0,0,0,0,100,100,0,0,1,2.5,0,2,140,140,38,1",
           "Style: WM,Noto Sans,30,&H70FFFFFF,&H70FFFFFF,&H90000000,&HFF000000,1,0,0,0,100,100,1,0,1,1,0,9,0,48,34,1",
           "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
           f"Dialogue: 1,{_ts(0, '.')},{_ts(total + 1, '.')},WM,,0,0,0,,{WATERMARK}"]
    srt = {"en": [], "zh": [], "en-zh": []}
    for n, (a, b, en, zh) in enumerate(subs, 1):
        ass += [f"Dialogue: 0,{_ts(a, '.')},{_ts(b, '.')},EN,,0,0,0,,{en}",
                f"Dialogue: 0,{_ts(a, '.')},{_ts(b, '.')},ZH,,0,0,0,,{zh}"]
        head = f"{n}\n{_ts(a, ',')} --> {_ts(b, ',')}\n"
        srt["en"].append(head + en + "\n")
        srt["zh"].append(head + zh + "\n")
        srt["en-zh"].append(head + en + "\n" + zh + "\n")
    (OUT / "subs.ass").write_text("\n".join(ass) + "\n", encoding="utf-8")
    for k, v in srt.items():
        (OUT / f"demo.{k}.srt").write_text("\n".join(v), encoding="utf-8")

asyncio.run(main())
