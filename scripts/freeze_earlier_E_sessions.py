"""Generic date-ranking helper. Individual adjudication is kept outside Git."""


def earlier_date_candidates(rows):
    """Rank actual acquisition dates, without inventing a same-day tie breaker."""
    if not rows or any(len(r["acquisition_dates"]) != 1 for r in rows):
        raise ValueError("Missing or multi-day acquisition date")
    day = min(r["acquisition_dates"][0] for r in rows)
    return [r for r in rows if r["acquisition_dates"] == [day]]
