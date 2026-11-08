from finn import db
from finn.classify.llm import LLM_SUBTYPES, SYSTEM_PROMPT, classify_batch_llm
from finn.classify.materiality import MODIFIERS, score_filing
from finn.classify.pipeline import classify_pending
from finn.classify.rules import classify_rules
from finn.llm import LLMError
from finn.models import Filing


def _f(i: int, desc: str = "General Updates", subject: str = "Something vague") -> Filing:
    return Filing(
        seq_id=str(i),
        symbol="X",
        company="X Ltd",
        nse_desc=desc,
        subject=subject,
        nse_summary="s" * 1000,
        filed_at="2026-11-01T10:00:00+05:30",
    )


class FakeRouter:
    def __init__(self, reply=None, error=False):
        self.calls: list[tuple[str, str, str]] = []
        self._reply = reply
        self._error = error

    def complete_json(self, task, system, user, *, doc_hash=""):
        import json

        self.calls.append((task, system, user))
        if self._error:
            raise LLMError("boom")
        if self._reply is not None:
            return self._reply
        ids = [it["id"] for it in json.loads(user)]
        return {"items": [{"id": i, "category": "capex", "subtype": "new_plant"} for i in ids]}


def test_batches_of_20():
    r = FakeRouter()
    out = classify_batch_llm(r, [_f(i) for i in range(45)])
    assert len(r.calls) == 3
    assert len(out) == 45
    c = out["0"]
    # capex has no scoring subtypes, so the free-form "new_plant" is dropped
    assert (c.category, c.subtype, c.by, c.confidence, c.noise) == ("capex", None, "llm", 0.7, False)
    assert r.calls[0][0] == "classify"


def test_prompt_is_compact():
    import json

    r = FakeRouter()
    classify_batch_llm(r, [_f(1)])
    item = json.loads(r.calls[0][2])[0]
    assert set(item) == {"id", "desc", "subject", "summary"}
    assert len(item["summary"]) == 400
    assert "routine = unclassified" in r.calls[0][1]


def test_bad_llm_output_defaults():
    reply = {
        "items": [
            {"id": "1", "category": "not_a_category"},
            {"id": "2", "category": "dividend"},
            {"id": "99", "category": "mna"},
        ]
    }
    out = classify_batch_llm(FakeRouter(reply), [_f(1), _f(2), _f(3)])
    assert out["1"].category == "unclassified" and out["1"].by == "default"
    assert out["2"].category == "dividend" and out["2"].by == "llm"
    assert out["3"].category == "unclassified" and out["3"].by == "default"
    assert "99" not in out


def test_malformed_reply_defaults_batch():
    out = classify_batch_llm(FakeRouter({"nope": 1}), [_f(1)])
    assert out["1"].by == "default" and out["1"].confidence == 0.0


def test_llmerror_defaults_whole_batch():
    out = classify_batch_llm(FakeRouter(error=True), [_f(i) for i in range(3)])
    assert len(out) == 3
    assert all(c.category == "unclassified" and c.by == "default" for c in out.values())


def test_pending_uses_rules_first(conn):
    rule_hit = _f(1, desc="Copy of Newspaper Publication", subject="Newspaper ad")
    vague = _f(2)
    db.upsert_filings(conn, [rule_hit, vague])
    r = FakeRouter()
    counts = classify_pending(conn, r)
    assert counts == {"rules": 1, "llm": 1, "default": 0}
    sent = [it for c in r.calls for it in __import__("json").loads(c[2])]
    assert [it["id"] for it in sent] == ["2"]
    assert db.unclassified_filings(conn) == []


def test_pending_without_router_defaults(conn):
    db.upsert_filings(conn, [_f(2)])
    assert classify_pending(conn, None) == {"rules": 0, "llm": 0, "default": 1}
    assert db.unclassified_filings(conn) == []


def test_one_bad_item_defaults_only_itself():
    reply = {
        "items": [
            {"id": "1", "category": "dividend", "subtype": None},
            {"id": 2, "category": "mna", "subtype": "stake_sale"},
            {"id": "3", "category": "capex", "subtype": 5},
            {"id": "4", "category": None},
            "garbage",
        ]
    }
    out = classify_batch_llm(FakeRouter(reply), [_f(1), _f(2), _f(3), _f(4)])
    assert (out["1"].category, out["1"].by) == ("dividend", "llm")
    assert (out["2"].category, out["2"].by) == ("mna", "llm")  # int id accepted
    # bad subtype is coerced to None; the valid category is kept
    assert (out["3"].category, out["3"].subtype, out["3"].by) == ("capex", None, "llm")
    assert (out["4"].category, out["4"].by) == ("unclassified", "default")


def test_items_not_a_list_defaults_batch():
    out = classify_batch_llm(FakeRouter({"items": "x"}), [_f(1)])
    assert out["1"].by == "default"


def test_valueerror_defaults_batch():
    class Boom(FakeRouter):
        def complete_json(self, *a, **k):
            raise ValueError("corrupt cache")

    assert classify_batch_llm(Boom(), [_f(1)])["1"].by == "default"


def _sent_ids(router: FakeRouter) -> list[str]:
    import json

    return [it["id"] for c in router.calls for it in json.loads(c[2])]


def test_pending_retries_default_rows_when_router_available(conn):
    db.upsert_filings(conn, [_f(2)])
    classify_pending(conn, None)  # keyless run: rule miss -> default
    assert db.get_filing(conn, "2")[1].by == "default"

    db.upsert_filings(conn, [_f(3)])  # a new rule miss arrives too
    r = FakeRouter()
    assert classify_pending(conn, r) == {"rules": 0, "llm": 2, "default": 0}
    assert sorted(_sent_ids(r)) == ["2", "3"]
    cls = db.get_filing(conn, "2")[1]
    assert (cls.category, cls.by) == ("capex", "llm")
    assert db.default_classified_filings(conn) == []


def test_pending_retry_that_fails_stays_default(conn):
    db.upsert_filings(conn, [_f(2)])
    classify_pending(conn, None)
    assert classify_pending(conn, FakeRouter(error=True)) == {"rules": 0, "llm": 0, "default": 1}
    assert [f.seq_id for f in db.default_classified_filings(conn)] == ["2"]


def test_pending_without_router_leaves_default_rows_alone(conn):
    db.upsert_filings(conn, [_f(2)])
    classify_pending(conn, None)
    db.upsert_filings(conn, [_f(3)])
    assert classify_pending(conn, None) == {"rules": 0, "llm": 0, "default": 1}  # only the new one
    assert [f.seq_id for f in db.default_classified_filings(conn)] == ["2", "3"]


def _reply(category, subtype, item_id="1"):
    return {"items": [{"id": item_id, "category": category, "subtype": subtype}]}


def test_llm_credit_rating_subtype_comes_from_the_rules():
    subject = "CRISIL Ratings has reaffirmed the long-term credit rating of the Company at AAA"
    f = _f(1, desc="General Updates", subject=subject)
    c = classify_batch_llm(FakeRouter(_reply("credit_rating", "rating_reaffirmation")), [f])["1"]
    assert (c.category, c.subtype, c.by) == ("credit_rating", "reaffirm", "llm")
    rule_path = classify_rules(_f(2, desc="Credit Rating- Others", subject=subject))
    assert rule_path.subtype == "reaffirm"
    assert score_filing(f, c, set()).score == score_filing(f, rule_path, set()).score == 24


def test_llm_management_change_subtype_comes_from_the_rules():
    subject = "Appointment of Ms. Asha Rao as an Independent Director of the Company"
    f = _f(1, desc="General Updates", subject=subject)
    c = classify_batch_llm(FakeRouter(_reply("management_change", "director_appointment")), [f])
    assert (c["1"].category, c["1"].subtype) == ("management_change", "independent")


def test_llm_subtype_kept_only_when_scoring_knows_it():
    cases = [
        (("earnings_call", "transcript"), "transcript"),
        (("earnings_call", " Transcript "), "transcript"),
        (("results", "presentation"), "presentation"),
        (("results", "transcript"), None),  # a real subtype, but of another category
        (("capex", "new_plant"), None),
        (("press_release", None), None),
    ]
    for (category, subtype), expected in cases:
        c = classify_batch_llm(FakeRouter(_reply(category, subtype)), [_f(1)])["1"]
        assert (c.category, c.subtype) == (category, expected), (category, subtype)


def test_llm_subtype_allowlist_is_the_modifier_table_and_is_in_the_prompt():
    expected: dict[str, set[str]] = {}
    for category, subtype in MODIFIERS:
        if category not in {"management_change", "credit_rating"}:  # derived by the rules
            expected.setdefault(category, set()).add(subtype)
    assert {k: set(v) for k, v in LLM_SUBTYPES.items()} == expected
    for category, subtypes in LLM_SUBTYPES.items():
        line = next(ln for ln in SYSTEM_PROMPT.splitlines() if ln.startswith(f"{category}: "))
        assert all(sub in line for sub in subtypes)
