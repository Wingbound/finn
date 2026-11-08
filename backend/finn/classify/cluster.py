"""Group scored filings into stories (same symbol + category within a time window)."""

from __future__ import annotations

from datetime import timedelta

from finn.models import ScoredFiling, Story


def _seq_key(seq_id: str) -> tuple[int, int, str]:
    # Numeric compare when digit strings; those sort before non-numeric ids.
    return (0, int(seq_id), seq_id) if seq_id.isdigit() else (1, 0, seq_id)


def _order(s: ScoredFiling) -> tuple:
    return (s.filing.filed_at, _seq_key(s.filing.seq_id))


def _headline(members: list[ScoredFiling]) -> ScoredFiling:
    # highest score; ties -> earliest filed_at, then lowest seq_id
    return min(members, key=lambda s: (-s.score, *_order(s)))


def cluster(scored: list[ScoredFiling], window_hours: int = 48) -> list[Story]:
    window = timedelta(hours=window_hours)
    groups: list[list[ScoredFiling]] = []
    open_by_key: dict[tuple, list[list[ScoredFiling]]] = {}

    for s in sorted(scored, key=_order):
        key = (s.filing.symbol, s.cls.category, s.tier == "noise")
        for g in open_by_key.get(key, []):
            if s.filing.filed_at - g[0].filing.filed_at <= window:
                g.append(s)
                break
        else:
            g = [s]
            groups.append(g)
            open_by_key.setdefault(key, []).append(g)

    stories = []
    for members in groups:
        head = _headline(members)
        first = members[0]
        stories.append(
            Story(
                id=f"{first.filing.symbol}:{first.cls.category}:{first.filing.seq_id}",
                symbol=first.filing.symbol,
                company=head.filing.company,
                category=first.cls.category,
                subtype=head.cls.subtype,
                score=head.score,
                tier=head.tier,
                headline=head,
                members=members,
                latest_at=max(m.filing.filed_at for m in members),
            )
        )
    stories.sort(key=lambda st: (st.score, st.latest_at), reverse=True)
    return stories
