"""The AI build history export: what it keeps, what it clips, and what it must never leak."""

from __future__ import annotations

import json

from scripts.export_history import redact, render_session


def test_redacts_personal_details_and_keys():
    text = (
        "mail me at someone.private@gmail.com or kerb me1220123@iitd.ac.in; entry 2022ME11234; "
        "files in /home/alice/Desktop/x; key AIzaSyA1234567890abcdefghijklmnopqrstu and gsk_abcdefghijklmnopqrstuvwxyz1234"
    )
    out = redact(text)
    for leak in (
        "someone.private",
        "iitd.ac.in",
        "me1220123",
        "2022ME11234",
        "/home/alice",
        "AIzaSy",
        "gsk_abc",
    ):
        assert leak not in out, leak
    assert "~/Desktop/x" in out


def test_keeps_public_addresses():
    out = redact("send to assessment@enam.com; Co-Authored-By: Claude <noreply@anthropic.com>")
    assert "assessment@enam.com" in out and "noreply@anthropic.com" in out


def _line(**d) -> str:
    return json.dumps(d)


def test_renders_turns_tools_and_clips_results(tmp_path):
    long = "x" * 2000
    lines = [
        _line(type="user", message={"role": "user", "content": "build FINN please"}),
        _line(
            type="assistant",
            message={
                "content": [
                    {"type": "thinking", "thinking": "private reasoning"},
                    {"type": "text", "text": "Starting with the backend."},
                    {
                        "type": "tool_use",
                        "id": "t1",
                        "name": "Bash",
                        "input": {
                            "command": "uv run pytest -q\necho done",
                            "description": "Run tests",
                        },
                    },
                ]
            },
        ),
        _line(
            type="user",
            message={"content": [{"type": "tool_result", "tool_use_id": "t1", "content": long}]},
        ),
        _line(
            type="user",
            isMeta=True,
            message={"content": "<system-reminder>internal</system-reminder>"},
        ),
        _line(type="attachment", attachment={"x": 1}),
        "not json",
    ]
    p = tmp_path / "s.jsonl"
    p.write_text("\n".join(lines))
    md = render_session(p)
    assert "build FINN please" in md
    assert "Starting with the backend." in md
    assert "Bash" in md and "Run tests" in md
    assert "private reasoning" not in md
    assert "internal" not in md
    assert "x" * 401 not in md and "x" * 100 in md  # clipped to 400 chars


def test_redacts_a_home_path_cut_short_by_clipping():
    assert "alice" not in redact("saved files only under /home/alice… [305 more characters]")
