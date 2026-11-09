"""Who is in, who is out: LLM extraction of management changes, guarded by grounding."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime

from finn import db
from finn.enrich import EnrichResult
from finn.enrich.grounding import (
    grounded_sentences,
    name_in_text,
    normalize,
    strip_honorifics,
)
from finn.enrich.pdftext import get_doc_text, relevant_window
from finn.ingest.nse import NSEUnavailable
from finn.llm.providers import LLMError
from finn.models import Filing, PersonChange, Story

log = logging.getLogger(__name__)

KIND = "people"
PROFILE_MAX_WORDS = 90
INCOMING = {"appointed", "redesignated"}
CHANGES = {"appointed", "resigned", "retired", "ceased", "redesignated", "other"}

PEOPLE_TERMS = [
    "appoint",
    "resign",
    "retire",
    "cessation",
    "cease",
    "designat",
    "brief profile",
    "annexure",
    "director",
    "officer",
    "key managerial",
    "senior management",
]

SYSTEM_PROMPT = """You read an Indian stock-exchange filing about a change in directors, key \
managerial personnel or senior management. List every person whose role changes.

Reply with JSON only: {"people":[{"name","role","change","effective","profile"}]}

- name: the person's full name as written in the filing.
- role: the role they take up or leave, as written (for example "Chairman", "Managing Director").
- change: one of
  "appointed": newly appointed or elected to a role (including re-appointment to a new term);
  "resigned": the person resigned or stepped down of their own accord;
  "retired": retirement or end of tenure by age or policy;
  "ceased": cessation for any other reason (death, removal, completion of term);
  "redesignated": moves to a different role, or the role's title changes;
  "other": anything else, for example a change in remuneration or committee membership.
- effective: the effective date or period exactly as the filing words it, else null.
- profile: copy the person's "Brief Profile" sentences verbatim from the filing, else null. \
Do not paraphrase, shorten inside a sentence, or add anything.

Use only the filing text; if unsure, omit the person."""


def extract_people(router, f: Filing, text: str) -> list[PersonChange]:
    """Ask the LLM, then keep only people and profile sentences the filing text supports."""
    user = f"SUBJECT: {f.subject}\n\nFILING TEXT:\n{relevant_window(text, PEOPLE_TERMS)}"
    reply = router.complete_json("bio", SYSTEM_PROMPT, user)
    raw = reply.get("people") if isinstance(reply, dict) else None
    if not isinstance(raw, list):
        return []
    out: list[PersonChange] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name_in_text(name, text):
            continue
        key = normalize(strip_honorifics(name))
        if key in seen:
            continue
        seen.add(key)
        change = item.get("change")
        if not isinstance(change, str) or change not in CHANGES:
            change = "other"
        profile = item.get("profile")
        out.append(
            PersonChange(
                name=name.strip(),
                role=_grounded_or_none(item.get("role"), text),
                change=change,
                effective=_grounded_or_none(item.get("effective"), text),
                profile=(
                    grounded_sentences(profile, text, PROFILE_MAX_WORDS)
                    if isinstance(profile, str)
                    else None
                ),
                incoming=change in INCOMING,
                source_seq_id=f.seq_id,
            )
        )
    return out


def _grounded_or_none(v: object, text: str) -> str | None:
    """A string field kept only if the filing text contains it."""
    if not isinstance(v, str) or not v.strip():
        return None
    return v.strip() if normalize(v) in normalize(text) else None


def enrich_people(conn: sqlite3.Connection, client, router, since: datetime) -> EnrichResult:
    """Extract people for management_change filings since `since` that have none saved yet.

    LLM and NSE failures are reported in `failed` and nothing is saved, so the filing is
    retried on the next refresh.
    """
    res = EnrichResult()
    for f, _cls in db.filings_missing_enrichment(conn, KIND, {"management_change"}, since):
        try:
            text = get_doc_text(conn, client, f.pdf_url) if f.pdf_url else (f.nse_summary or "")
            if not text.strip():
                db.save_enrichment(conn, f.seq_id, KIND, {"people": [], "reason": "no text"}, None)
                res.empty += 1
                continue
            people = extract_people(router, f, text)
        except (LLMError, NSEUnavailable) as e:
            log.warning("people enrichment failed for %s: %s", f.seq_id, e)
            res.failed[f.seq_id] = str(e)
            continue
        except Exception as e:
            log.exception("people enrichment crashed for %s", f.seq_id)
            res.failed[f.seq_id] = f"{type(e).__name__}: {e}"
            continue
        payload = {"people": [p.model_dump(mode="json") for p in people]}
        db.save_enrichment(conn, f.seq_id, KIND, payload, router.last_model)
        res.done += 1
    return res


def attach_people(conn: sqlite3.Connection, stories: list[Story]) -> None:
    """Give each management_change story the saved people of its members.

    Deduped by normalized name (first appearance wins), incoming people first, otherwise
    in order of first appearance across members in story order.
    """
    targets = [st for st in stories if st.category == "management_change"]
    ids = [m.filing.seq_id for st in targets for m in st.members]
    saved = db.get_enrichments(conn, ids, KIND)
    for st in targets:
        seen: set[str] = set()
        found: list[PersonChange] = []
        for m in st.members:
            for raw in saved.get(m.filing.seq_id, {}).get("people", []):
                p = PersonChange.model_validate(raw)
                key = normalize(strip_honorifics(p.name))
                if key not in seen:
                    seen.add(key)
                    found.append(p)
        st.people = [p for p in found if p.incoming] + [p for p in found if not p.incoming]
