# Task 7 report
Implemented finn/classify/materiality.py, cluster.py; ScoredFiling/Story/Tier in models.py; tests test_materiality.py, test_cluster.py.
Noise filings are clustered separately from non-noise (key includes noise flag) so a hidden noise story never swallows a real one.
Tie-break per R4 (score, filed_at, numeric seq_id). Reason format "<label> ×<mult>", "you follow <cat> +10".
TDD note: tests and implementation were written together; no separate RED run was captured. One test of mine had a wrong expected ordering (results 90 > mna 85), fixed in test.
Result: full suite passes, ruff clean.
