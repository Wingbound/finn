# AI build history

- `claude-code-session.md`: the Claude Code session that built FINN, from the first prompt on 8 Nov 2026. It is exported with `backend/scripts/export_history.py`. The export keeps the messages and one line per tool call, clips each tool result to 400 characters, and drops thinking blocks. Personal details are redacted. Lines that showed unrelated personal files were removed by hand.
- `planN-*/`: one folder per plan, holding its task ledger, the briefs and reports for each task, and its final review. The plans themselves are in `docs/superpowers/plans/`.
  - `-sdd` folders ran with a fresh subagent per task and a review after each task.
  - `-inline` folders ran in the main session, with one review at the end.
