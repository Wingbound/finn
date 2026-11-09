"""Render Claude Code session transcripts (*.jsonl) as readable, redacted Markdown.

Run: uv run python scripts/export_history.py SESSION.jsonl [...] --out DIR

What it keeps:
- the user's messages;
- Claude's replies;
- each tool call as one line (tool, plus its description or first line);
- each tool result, clipped to 400 characters.

What it drops: thinking blocks, system reminders and other internal bookkeeping.

What it redacts, without needing to know whose history it is:
- every email address except a short public allowlist;
- IIT-style entry numbers and Kerberos IDs;
- home-directory paths;
- anything shaped like an API key.

Read the output before publishing it: redaction is a safety net, not a guarantee.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from functools import lru_cache
from pathlib import Path

CLIP = 400
PUBLIC_EMAILS = {"assessment@enam.com", "noreply@anthropic.com"}
NOREPLY = "@users.noreply.github.com"

_L = r"(?<![A-Za-z0-9])"  # a boundary that, unlike \b, also holds next to "_"
_R = r"(?![A-Za-z0-9])"
# Emails, including the regex-escaped (a\.b@c\.com) and percent-encoded (a%40c.com) forms
# a leak scan or a URL produces.
_EMAIL = re.compile(r"[A-Za-z0-9._%+\\-]+(?:@|%40)[A-Za-z0-9\\.-]+\.[A-Za-z]{2,}")
_SPELLED = re.compile(
    r"[A-Za-z0-9._%+-]+\s*[\[(]\s*at\s*[\])]\s*[A-Za-z0-9-]+(?:\s*(?:[\[(]\s*dot\s*[\])]|\.)\s*[A-Za-z0-9-]+)+",
    re.IGNORECASE,
)
_RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(_L + r"20\d{2}[A-Z]{2,3}\d{4,5}" + _R, re.IGNORECASE),
        "[entry number]",
    ),  # 2022ME11234
    (re.compile(_L + r"[A-Z]{2,3}\d{7}(?![0-9])", re.IGNORECASE), "[kerberos id]"),  # me1220123
    (re.compile(r"/home/[A-Za-z0-9._-]+"), "~"),
    (re.compile(r"/Users/[A-Za-z0-9._-]+"), "~"),
    (re.compile(r"[A-Za-z]:\\+Users\\+[^\\\s]+"), "~"),  # C:\Users\Name
    (re.compile(r"-home-[A-Za-z0-9._]+-"), "-home-[user]-"),  # ~/.claude/projects/-home-x-...
    (re.compile(r"AIza[0-9A-Za-z_-]{20,}"), "[key]"),
    (re.compile(r"gsk_[0-9A-Za-z]{20,}"), "[key]"),
    (re.compile(r"hf_[0-9A-Za-z]{20,}"), "[key]"),
    (re.compile(r"github_pat_[0-9A-Za-z_]{20,}"), "[key]"),
    (re.compile(r"sk-(?:proj-|ant-)?[0-9A-Za-z_-]{20,}"), "[key]"),
    (re.compile(r"(?:ghp|gho|ghu|ghs|ghr|vercel)_[0-9A-Za-z]{20,}"), "[key]"),
    # KEY=value or token: value, whatever the value looks like
    (
        re.compile(
            r"(?i)\b([A-Z0-9_]*(?:API_?KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*)(\s*[=:]\s*)[^\s\"',;]{12,}"
        ),
        r"\1\2[redacted]",
    ),
]


@lru_cache(maxsize=1)
def load_literals() -> tuple[str, ...]:
    """Exact strings to remove (your email, entry number, username, phone), one per line, from
    the untracked file named by FINN_REDACT_FILE. Nothing personal has to live in this repo."""
    path = os.environ.get("FINN_REDACT_FILE")
    if not path or not Path(path).exists():
        return ()
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return tuple(x.strip() for x in lines if x.strip() and not x.strip().startswith("#"))


def _literal_forms(value: str) -> set[str]:
    """The value as written, regex-escaped, percent-encoded, and with spaces as dashes."""
    return {
        value,
        re.escape(value),
        value.replace("@", "%40"),
        re.escape(value).replace("@", "%40"),
        value.replace(" ", "-"),
        value.replace(" ", "_"),
    }


def _email(m: re.Match[str]) -> str:
    addr = m.group(0)
    plain = addr.replace("\\", "").replace("%40", "@").lower()
    return addr if plain in PUBLIC_EMAILS or plain.endswith(NOREPLY) else "[email]"


def redact(text: str) -> str:
    for value in load_literals():
        for form in sorted(_literal_forms(value), key=len, reverse=True):
            text = re.sub(re.escape(form), "[redacted]", text, flags=re.IGNORECASE)
    text = _SPELLED.sub("[email]", text)
    text = _EMAIL.sub(_email, text)
    for pattern, repl in _RULES:
        text = pattern.sub(repl, text)
    return text


def _clip(text: str, n: int = CLIP) -> str:
    text = redact(text).strip()  # redact first: an identifier cut at the clip would escape
    return text if len(text) <= n else f"{text[:n]}… [{len(text) - n} more characters]"


def _result_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                parts.append(str(b.get("text", "")))
            elif isinstance(b, dict) and b.get("type") == "image":
                parts.append("[image]")
        return "\n".join(parts)
    return ""


def _tool_line(block: dict) -> str:
    name = block.get("name", "tool")
    inp = block.get("input") or {}
    what = (
        inp.get("description")
        or inp.get("file_path")
        or inp.get("pattern")
        or inp.get("query")
        or (str(inp.get("command", "")).splitlines() or [""])[0]
        or inp.get("prompt", "")[:120]
    )
    return f"- **{name}**: {str(what).strip()}"


def _internal(text: str) -> bool:
    t = text.lstrip()
    return t.startswith(
        ("<system-reminder>", "<local-command", "<command-name>", "<task-notification>", "Caveat:")
    ) or ("[SYSTEM NOTIFICATION" in t[:200])


def render_session(path: Path) -> str:
    out: list[str] = [f"# Session {path.stem}\n"]
    entries = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            entries.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    # A subagent's own transcript is all sidechain; in a main session, sidechain lines are noise.
    subagent = bool(entries) and all(
        d.get("isSidechain") for d in entries if d.get("type") in ("user", "assistant")
    )
    for d in entries:
        kind = d.get("type")
        if (
            kind not in ("user", "assistant")
            or d.get("isMeta")
            or (d.get("isSidechain") and not subagent)
        ):
            continue
        content = (d.get("message") or {}).get("content")
        if kind == "user" and d.get("isCompactSummary"):
            out.append(
                f"\n> *Context summary after compaction:* {_clip(_result_text(content) or str(content), 1200)}\n"
            )
            continue
        if isinstance(content, str):
            if kind == "user" and not _internal(content):
                out.append(f"\n## You\n\n{content.strip()}\n")
            continue
        if not isinstance(content, list):
            continue
        texts = [b for b in content if isinstance(b, dict) and b.get("type") == "text"]
        tools = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]
        results = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"]
        if kind == "user":
            for b in texts:
                if not _internal(str(b.get("text", ""))):
                    out.append(f"\n## You\n\n{str(b.get('text', '')).strip()}\n")
            for b in results:
                body = _clip(_result_text(b.get("content")))
                if body:
                    quoted = "\n".join(f"> {line}" for line in body.splitlines())
                    out.append(f"{quoted}\n")
        else:
            for b in texts:
                text = str(b.get("text", "")).strip()
                if text:
                    out.append(f"\n## Claude\n\n{text}\n")
            for b in tools:
                out.append(_tool_line(b))
    return redact("\n".join(out)) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("sessions", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    for s in args.sessions:
        md = render_session(s)
        target = args.out / f"{s.stem}.md"
        target.write_text(md, encoding="utf-8")
        print(f"{target}: {len(md) / 1_000_000:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
