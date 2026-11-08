from finn import db
from finn.classify.llm import classify_batch_llm
from finn.classify.pipeline import classify_pending
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
    assert (c.category, c.subtype, c.by, c.confidence, c.noise) == ("capex", "new_plant", "llm", 0.7, False)
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
