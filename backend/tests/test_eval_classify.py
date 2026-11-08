import json
from datetime import datetime
from pathlib import Path

import httpx
import respx

from finn.classify.rules import AMBIGUOUS_DESCS
from finn.config import Settings
from finn.llm import LLMRouter
from finn.models import CATEGORIES, IST, Classification, Filing
from scripts import eval_classify as ev

FIX = Path(__file__).parent / "fixtures"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
ROW_KEYS = {"seq_id", "nse_desc", "subject", "summary", "category", "subtype", "noise"}


def _gold(seq_id, category, noise=False, subject="subject text"):
    return {
        "seq_id": seq_id,
        "nse_desc": "d",
        "subject": subject,
        "summary": None,
        "category": category,
        "subtype": None,
        "noise": noise,
    }


def _pred(category, noise=False, by="rules"):
    return Classification(category=category, noise=noise, by=by, confidence=0.9)


def _filing(seq_id, desc, subject):
    return Filing(
        seq_id=seq_id,
        symbol="X",
        company="X",
        nse_desc=desc,
        subject=subject,
        filed_at=datetime(2026, 11, 1, 10, 0, tzinfo=IST),
    )


# --- gold set integrity ---------------------------------------------------------------


def test_gold_set_shape_and_stratification():
    gold = ev.load_gold()
    fixture = {
        str(r["seq_id"]): r for r in json.loads((FIX / "nse" / "portfolio_month.json").read_text())
    }
    assert len(gold) >= 80
    assert len({g["seq_id"] for g in gold}) == len(gold)
    for g in gold:
        assert ROW_KEYS <= set(g) <= ROW_KEYS | {"notes"}
        assert g["category"] in CATEGORIES and isinstance(g["noise"], bool)
        assert not g["noise"] or g["category"] == "unclassified"
        raw = fixture[g["seq_id"]]
        assert (g["nse_desc"], g["subject"]) == (raw["desc"], raw["attchmntText"])
    assert {r["desc"] for r in fixture.values()} <= {g["nse_desc"] for g in gold}
    assert sum(g["nse_desc"] in AMBIGUOUS_DESCS for g in gold) >= 25


# --- metrics ----------------------------------------------------------------------------


def test_noise_rows_match_on_noise_flag_only():
    assert ev.is_match(_gold("1", "unclassified", noise=True), _pred("unclassified", noise=True))
    assert ev.is_match(_gold("1", "unclassified", noise=True), _pred("results", noise=True))
    assert not ev.is_match(_gold("1", "unclassified", noise=True), _pred("unclassified"))


def test_other_rows_match_on_category():
    assert ev.is_match(_gold("1", "results"), _pred("results"))
    assert not ev.is_match(_gold("1", "results"), _pred("press_release"))


def test_evaluate_counts():
    gold = [
        _gold("1", "results"),  # material, hit
        _gold("2", "mna"),  # material, miss
        _gold("3", "investor_meetings"),  # not material, hit
        _gold("4", "unclassified", noise=True),  # noise, hit
        _gold("5", "insider_trading", subject="x" * 100),  # base 50: material, miss
    ]
    preds = {
        "1": _pred("results"),
        "2": _pred("unclassified", by="default"),
        "3": _pred("investor_meetings"),
        "4": _pred("unclassified", noise=True),
        "5": _pred("press_release", by="llm"),
    }
    r = ev.evaluate(gold, preds, rule_hits={"1", "3", "4"})
    assert (r["n"], r["correct"]) == (5, 3)
    assert r["accuracy"] == 0.6
    assert (r["material_n"], r["material_correct"]) == (3, 1)
    assert r["rules_coverage"] == 0.6
    assert r["misses"] == [
        {"seq_id": "2", "gold": "mna", "predicted": "unclassified", "subject": "subject text"},
        {
            "seq_id": "5",
            "gold": "insider_trading",
            "predicted": "press_release",
            "subject": "x" * 80,
        },
    ]


def test_rules_precision_and_default_matches():
    gold = [
        _gold("1", "results"),
        _gold("2", "mna"),
        _gold("3", "unclassified"),
        _gold("4", "unclassified"),
    ]
    preds = {
        "1": _pred("results"),  # rule hit, right
        "2": _pred("press_release"),  # rule hit, wrong
        "3": _pred("unclassified", by="default"),  # rule miss, default happens to match
        "4": _pred("unclassified"),  # rule hit, right
    }
    r = ev.evaluate(gold, preds, rule_hits={"1", "2", "4"})
    assert (r["rules_correct"], r["rules_hits"]) == (2, 3)
    assert r["rules_precision"] == 2 / 3
    assert (r["default_matches"], r["correct"]) == (1, 3)
    out = ev.render("m", r)
    assert "| rules precision (rows the rules labelled) | 66.7% (2/3) |" in out
    assert "| correct rows that are default `unclassified` matches | 1 of 3 |" in out


def test_miss_labels_show_noise():
    gold = [_gold("1", "unclassified", noise=True), _gold("2", "results")]
    preds = {"1": _pred("unclassified"), "2": _pred("unclassified", noise=True)}
    misses = ev.evaluate(gold, preds, rule_hits=set())["misses"]
    assert [(m["gold"], m["predicted"]) for m in misses] == [
        ("noise", "unclassified"),
        ("results", "noise"),
    ]


# --- prediction -------------------------------------------------------------------------


def test_predict_rules_only_defaults_the_misses():
    hit = _filing("1", "Copy of Newspaper Publication", "Newspaper ad")
    miss = _filing("2", "Totally new NSE desc", "Something")
    preds, rule_hits = ev.predict([hit, miss], router=None)
    assert rule_hits == {"1"}
    assert preds["1"].noise and preds["1"].by == "rules"
    assert (preds["2"].category, preds["2"].by) == ("unclassified", "default")


@respx.mock
def test_predict_sends_only_rule_misses_to_llm(conn):
    seen = []

    def groq(req):
        items = json.loads(json.loads(req.content)["messages"][1]["content"])
        seen.extend(i["id"] for i in items)
        content = json.dumps({"items": [{"id": i["id"], "category": "capex"} for i in items]})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    respx.post(GROQ_URL).mock(side_effect=groq)
    router = LLMRouter(conn, Settings(_env_file=None, groq_api_key="k"))
    hit = _filing("1", "Copy of Newspaper Publication", "Newspaper ad")
    miss = _filing("2", "Totally new NSE desc", "Something")
    preds, rule_hits = ev.predict([hit, miss], router=router)
    assert seen == ["2"] and rule_hits == {"1"}
    assert (preds["2"].category, preds["2"].by) == ("capex", "llm")


# --- CLI --------------------------------------------------------------------------------


def test_cli_rules_only_prints_table(capsys):
    assert ev.main(["--no-llm"]) == 0
    out = capsys.readouterr().out
    assert "overall accuracy" in out and "material-category accuracy" in out
    assert "rules coverage" in out and "Misses" in out
    assert "rules precision" in out and "default `unclassified` matches" in out


def test_cli_llm_mode_without_key_exits_with_hint(monkeypatch, capsys):
    monkeypatch.setattr(ev, "get_settings", lambda: Settings(_env_file=None, groq_api_key=""))
    assert ev.main([]) == 2
    assert "--no-llm" in capsys.readouterr().out


@respx.mock
def test_cli_llm_mode_classifies_rule_misses(tmp_path, monkeypatch, capsys):
    serving = tmp_path / "finn.sqlite"
    settings = Settings(_env_file=None, groq_api_key="k", data_dir=tmp_path, db_path=serving)
    monkeypatch.setattr(ev, "get_settings", lambda: settings)

    def groq(req):
        items = json.loads(json.loads(req.content)["messages"][1]["content"])
        content = json.dumps({"items": [{"id": i["id"], "category": "results"} for i in items]})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    respx.post(GROQ_URL).mock(side_effect=groq)
    assert ev.main([]) == 0
    out = capsys.readouterr().out
    assert "Rules + LLM (groq/" in out and "LLM calls this run" in out
    assert not serving.exists()  # the LLM cache lives in its own DB, never the serving one
    assert settings.llm_cache_path.exists()
