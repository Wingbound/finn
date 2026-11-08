import json
from pathlib import Path

from finn.classify.cluster import cluster
from finn.classify.materiality import score_filing
from finn.classify.rules import classify_rules
from finn.ingest.nse import parse_announcement
from finn.models import Classification, Filing

FIXTURES = Path(__file__).parent / "fixtures" / "nse"


def _scored(seq, ts, subject="s", pdf=None, sym="X", cat="results"):
    f = Filing(
        seq_id=seq, symbol=sym, company=f"{sym} Ltd", nse_desc="d", subject=subject,
        pdf_url=pdf, filed_at=ts,
    )
    c = Classification(category=cat, by="rules", confidence=1.0)
    return score_filing(f, c, set())


def test_reliance_results_cluster():
    wanted = {"106837394", "106837395", "106837406", "106837413"}
    raw = json.loads((FIXTURES / "RELIANCE.json").read_text())
    scored = []
    for r in raw:
        f = parse_announcement(r)
        if f.seq_id in wanted:
            cls = classify_rules(f)
            assert cls is not None and cls.category == "results"
            scored.append(score_filing(f, cls, set()))
    assert len(scored) == 4
    stories = cluster(scored)
    assert len(stories) == 1
    st = stories[0]
    assert st.category == "results" and len(st.members) == 4
    assert st.headline.filing.nse_desc == "Outcome of Board Meeting"
    assert st.headline.filing.seq_id == "106837394"
    assert st.id == "RELIANCE:results:106837394"


def test_same_subject_filings_one_story():
    a = _scored("1", "2026-11-01T10:00:00+05:30", "Same", "http://a.pdf")
    b = _scored("2", "2026-11-01T10:00:00+05:30", "Same", "http://b.pdf")
    stories = cluster([a, b])
    assert len(stories) == 1 and len(stories[0].members) == 2
    assert {m.filing.pdf_url for m in stories[0].members} == {"http://a.pdf", "http://b.pdf"}


def test_far_apart_same_category_not_merged():
    a = _scored("1", "2026-11-01T10:00:00+05:30")
    b = _scored("2", "2026-11-04T10:00:00+05:30")
    assert len(cluster([a, b])) == 2


def test_different_symbol_or_category_not_merged():
    a = _scored("1", "2026-11-01T10:00:00+05:30")
    b = _scored("2", "2026-11-01T10:00:00+05:30", sym="Y")
    c = _scored("3", "2026-11-01T10:00:00+05:30", cat="mna")
    assert len(cluster([a, b, c])) == 3


def test_window_anchored_to_first_filing_and_sorted():
    a = _scored("1", "2026-11-01T10:00:00+05:30")
    b = _scored("2", "2026-11-02T20:00:00+05:30")  # 34h
    c = _scored("3", "2026-11-03T12:00:00+05:30")  # 50h from first -> new story
    m = _scored("4", "2026-11-03T13:00:00+05:30", cat="mna")
    stories = cluster([c, b, a, m])
    assert [s.id for s in stories] == ["X:results:3", "X:results:1", "X:mna:4"]
    assert stories[1].latest_at == b.filing.filed_at
    assert len(stories[1].members) == 2


def test_numeric_seq_tiebreak():
    a = _scored("9", "2026-11-01T10:00:00+05:30")
    b = _scored("10", "2026-11-01T10:00:00+05:30")
    assert cluster([b, a])[0].headline.filing.seq_id == "9"
