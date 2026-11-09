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


# ---- Plan 5 review I3: realistic forms of the identifiers ----

import pytest

LEAKS = {
    "underscore-joined entry number": (
        "JD_2022ME11234.pdf and 2022ME11234_resume",
        ["2022ME11234"],
    ),
    "underscore-joined kerberos": ("user_me1220123_x and id:me1220123abc", ["me1220123"]),
    "uppercase kerberos": ("ME1220123 or Me1220123", ["ME1220123", "Me1220123"]),
    "lowercase entry number": ("2022me11234", ["2022me11234"]),
    "regex-escaped email": (r"grep someone\.private@gmail\.com", ["someone", "private@"]),
    "percent-encoded email": ("mailto:someone%40gmail.com", ["someone"]),
    "spelled-out email": (
        "someone (at) gmail (dot) com, other [at] iitd [dot] ac [dot] in",
        ["someone", "other"],
    ),
    "windows path": (r"C:\Users\Alice\Documents\cv.pdf", ["Alice"]),
    "dashed project path": ("projects/-home-alice-Desktop-Sem-9/x.jsonl", ["alice"]),
    "openai project key": ("sk-proj-abcdefghijklmnopqrstuvwx1234", ["abcdefghijkl"]),
    "anthropic key": ("sk-ant-api03-abcdefghijklmnopqrstuvwxyz", ["abcdefghijkl"]),
    "github fine-grained token": ("github_pat_11ABCDEFG0123456789_abcdefghijklmnop", ["11ABCDEFG"]),
    "key assignment": (
        "GEMINI_API_KEY=abcdefghijklmnop12345 and token: zyxwvutsrqponmlk9876",
        ["abcdefghijklmnop12345", "zyxwvutsrqponmlk9876"],
    ),
}


@pytest.mark.parametrize("case", sorted(LEAKS))
def test_redacts(case):
    text, secrets = LEAKS[case]
    out = redact(text)
    for s in secrets:
        assert s not in out, (case, out)


def test_the_noreply_allowlist_is_anchored():
    assert "12345+someone@users.noreply.github.com" in redact(
        "12345+someone@users.noreply.github.com"
    )
    assert "spy" not in redact("spy@fake-users.noreply.github.com")


def test_literal_identifiers_from_a_private_file(tmp_path, monkeypatch):
    f = tmp_path / "redact.txt"
    f.write_text("Priya Sharma\npriya.sharma@example.org\n# a comment\n")
    monkeypatch.setenv("FINN_REDACT_FILE", str(f))
    from scripts import export_history

    export_history.load_literals.cache_clear()
    out = redact(r"PRIYA SHARMA wrote to priya\.sharma@example\.org and priya.sharma%40example.org")
    assert "priya" not in out.lower()
    export_history.load_literals.cache_clear()


def test_an_identifier_cut_by_clipping_is_still_redacted(tmp_path):
    lead = "y" * 380
    lines = [
        _line(
            type="assistant",
            message={
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "x"}}
                ]
            },
        ),
        _line(
            type="user",
            message={
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "t1",
                        "content": f"{lead} someone.private@gmail.com tail",
                    }
                ]
            },
        ),
    ]
    p = tmp_path / "s.jsonl"
    p.write_text("\n".join(lines))
    assert "someone" not in render_session(p)


def test_task_notifications_are_not_shown_as_the_user(tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_text(
        _line(type="user", message={"content": "<task-notification>\n<task-id>x</task-id> done"})
    )
    assert "## You" not in render_session(p)


def test_a_subagent_transcript_renders(tmp_path):
    p = tmp_path / "agent.jsonl"
    p.write_text(
        "\n".join(
            [
                _line(type="user", isSidechain=True, message={"content": "Implement task 3"}),
                _line(
                    type="assistant",
                    isSidechain=True,
                    message={"content": [{"type": "text", "text": "Done; 12 tests pass."}]},
                ),
            ]
        )
    )
    md = render_session(p)
    assert "Implement task 3" in md and "Done; 12 tests pass." in md
