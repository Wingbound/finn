"""Classification eval against the hand-labelled gold set.

Run: uv run python scripts/eval_classify.py [--no-llm]

Rules run first; with the LLM (default) the rule misses go to classify_batch_llm, with
--no-llm they get the pipeline's default (unclassified). Prints a Markdown summary.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from finn import db
from finn.classify.llm import classify_batch_llm
from finn.classify.materiality import BASE_SCORES
from finn.classify.rules import classify_rules
from finn.config import get_settings, route_for
from finn.ingest.nse import parse_announcement
from finn.llm import LLMRouter
from finn.llm.providers import PROVIDERS
from finn.models import Classification, Filing

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
GOLD_PATH = FIXTURES / "gold" / "classification.jsonl"
FILINGS_PATH = FIXTURES / "nse" / "portfolio_month.json"
MATERIAL_BASE = 45
SUBJECT_CHARS = 80


def load_gold(path: Path = GOLD_PATH) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def load_filings(seq_ids: list[str], path: Path = FILINGS_PATH) -> list[Filing]:
    """The full fixture filings for the gold rows, in gold order."""
    by_id = {str(r["seq_id"]): r for r in json.loads(path.read_text(encoding="utf-8"))}
    return [parse_announcement(by_id[s]) for s in seq_ids]


def predict(
    filings: list[Filing], router: LLMRouter | None
) -> tuple[dict[str, Classification], set[str]]:
    """Rules first; misses go to the LLM (or default). Returns predictions and rule-hit ids."""
    preds: dict[str, Classification] = {}
    misses: list[Filing] = []
    for f in filings:
        c = classify_rules(f)
        if c is None:
            misses.append(f)
        else:
            preds[f.seq_id] = c
    rule_hits = set(preds)
    if router is not None:
        preds.update(classify_batch_llm(router, misses))
    else:
        for f in misses:
            preds[f.seq_id] = Classification(category="unclassified", by="default", confidence=0.0)
    return preds, rule_hits


def _label(category: str, noise: bool) -> str:
    return "noise" if noise else category


def is_match(gold: dict, pred: Classification) -> bool:
    """Noise rows match when the prediction is noise; other rows match on category."""
    if gold["noise"]:
        return pred.noise
    return pred.category == gold["category"]


def evaluate(gold: list[dict], preds: dict[str, Classification], rule_hits: set[str]) -> dict:
    hit = {g["seq_id"]: is_match(g, preds[g["seq_id"]]) for g in gold}
    material = [g for g in gold if BASE_SCORES[g["category"]] >= MATERIAL_BASE]
    n, correct = len(gold), sum(hit.values())
    material_correct = sum(hit[g["seq_id"]] for g in material)
    return {
        "n": n,
        "correct": correct,
        "accuracy": correct / n if n else 0.0,
        "material_n": len(material),
        "material_correct": material_correct,
        "material_accuracy": material_correct / len(material) if material else 0.0,
        "rules_hits": len(rule_hits),
        "rules_coverage": len(rule_hits) / n if n else 0.0,
        "misses": [
            {
                "seq_id": g["seq_id"],
                "gold": _label(g["category"], g["noise"]),
                "predicted": _label(preds[g["seq_id"]].category, preds[g["seq_id"]].noise),
                "subject": g["subject"][:SUBJECT_CHARS],
            }
            for g in gold
            if not hit[g["seq_id"]]
        ],
    }


def render(mode: str, r: dict) -> str:
    def pct(num: int, den: int) -> str:
        return f"{100 * num / den:.1f}% ({num}/{den})" if den else "n/a"

    lines = [
        f"### {mode}",
        "",
        "| metric | value |",
        "|---|---|",
        f"| rows | {r['n']} |",
        f"| overall accuracy | {pct(r['correct'], r['n'])} |",
        (
            f"| material-category accuracy (gold base ≥ {MATERIAL_BASE}) | "
            f"{pct(r['material_correct'], r['material_n'])} |"
        ),
        f"| rules coverage | {pct(r['rules_hits'], r['n'])} |",
        "",
        f"Misses ({len(r['misses'])}): seq_id · gold → predicted · subject",
        "",
    ]
    lines += [
        f"- {m['seq_id']} · {m['gold']} → {m['predicted']} · {m['subject']}" for m in r["misses"]
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-llm", action="store_true", help="rules only; misses -> unclassified")
    args = parser.parse_args(argv)

    gold = load_gold()
    filings = load_filings([g["seq_id"] for g in gold])
    if args.no_llm:
        preds, rule_hits = predict(filings, router=None)
        print(render("Rules only (`--no-llm`)", evaluate(gold, preds, rule_hits)))
        return 0

    settings = get_settings()
    provider, model = route_for("classify", settings)
    _call, _parse, key_attr, key_name = PROVIDERS[provider]
    if not getattr(settings, key_attr):
        print(f"{key_name} is empty; set it or run with --no-llm")
        return 2
    conn = db.connect(settings.db_path)  # reuses the LLM response cache across runs
    try:
        db.init_db(conn)
        router = LLMRouter(conn, settings)
        before = router.stats()
        preds, rule_hits = predict(filings, router)
        print(render(f"Rules + LLM ({provider}/{model})", evaluate(gold, preds, rule_hits)))
        after = router.stats()
        print("\nLLM calls this run:", {k: after[k] - before[k] for k in after})
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
