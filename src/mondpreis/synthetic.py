"""Constructed price histories with known-correct verdicts.

These are not random test data. Each scenario reproduces a specific pattern
from the case law or from the directive's text, so the expected findings are
derivable from the law rather than from whatever the engine currently does.
That ordering matters: the scenarios are the specification, and the engine is
judged against them.

Sale dates are anchored to Black Friday 2026 (27 November) because that is the
window the enforcement sweeps actually look at.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from .models import Observation

BLACK_FRIDAY_2026 = date(2026, 11, 27)

PRODUCT = "espresso-machine-x1"


def _steady(
    retailer: str,
    start: date,
    days: int,
    price: str,
    product_id: str = PRODUCT,
) -> list[Observation]:
    """One observation per day at a flat price."""
    return [
        Observation(
            product_id=product_id,
            retailer=retailer,
            observed_on=start + timedelta(days=i),
            price=Decimal(price),
        )
        for i in range(days)
    ]


def _sale(
    retailer: str,
    start: date,
    days: int,
    price: str,
    reference: str | None,
    pct: str | None,
    product_id: str = PRODUCT,
) -> list[Observation]:
    """One observation per day of an advertised reduction."""
    return [
        Observation(
            product_id=product_id,
            retailer=retailer,
            observed_on=start + timedelta(days=i),
            price=Decimal(price),
            reference_price=Decimal(reference) if reference is not None else None,
            advertised_discount_pct=Decimal(pct) if pct is not None else None,
        )
        for i in range(days)
    ]


def compliant() -> list[Observation]:
    """A lawful reduction. 100 for 40 days, then 70 off a stated prior of 100.

    Expect: no findings. This scenario is the one that catches an engine that
    has become trigger-happy.
    """
    start = BLACK_FRIDAY_2026 - timedelta(days=40)
    return (
        _steady("cleanshop.example", start, 40, "100.00")
        + _sale("cleanshop.example", BLACK_FRIDAY_2026, 4, "70.00", "100.00", "30")
    )


def mondpreis() -> list[Observation]:
    """The textbook inflation. 100 for 35 days, lifted to 150 for the last 5,
    then advertised as 30% off 150.

    Expect: REFERENCE_ABOVE_LOW (150 vs a 100 low), PERCENT_OVERSTATED (the
    price actually rose), and SHORT_LIVED_REFERENCE (150 held 5 days).
    """
    start = BLACK_FRIDAY_2026 - timedelta(days=40)
    return (
        _steady("moonshop.example", start, 35, "100.00")
        + _steady("moonshop.example", start + timedelta(days=35), 5, "150.00")
        + _sale("moonshop.example", BLACK_FRIDAY_2026, 4, "105.00", "150.00", "30")
    )


def aldi_sued() -> list[Observation]:
    """C-330/23. The trader cites an older, higher price rather than the
    30-day low, and computes the percentage from it.

    100 for the first 20 days, 80 for the 20 days before the sale, then 70
    advertised as 30% off a stated prior of 100.

    Expect: REFERENCE_ABOVE_LOW (100 vs the 80 low) and PERCENT_OVERSTATED
    (the true reduction off 80 is 12.5%, not 30%). This is the exact holding
    the CJEU handed down in September 2024.
    """
    start = BLACK_FRIDAY_2026 - timedelta(days=40)
    return (
        _steady("aldi-pattern.example", start, 20, "100.00")
        + _steady("aldi-pattern.example", start + timedelta(days=20), 20, "80.00")
        + _sale("aldi-pattern.example", BLACK_FRIDAY_2026, 4, "70.00", "100.00", "30")
    )


def missing_reference() -> list[Observation]:
    """A bare percentage with no prior price shown. The arithmetic happens to
    be honest, which is what makes this a clean test of Art. 6a(1) alone.

    Expect: MISSING_REFERENCE, and nothing else.
    """
    start = BLACK_FRIDAY_2026 - timedelta(days=40)
    return (
        _steady("barepct.example", start, 40, "100.00")
        + _sale("barepct.example", BLACK_FRIDAY_2026, 4, "70.00", None, "30")
    )


def insufficient_history() -> list[Observation]:
    """A collector that started 10 days ago cannot verify a 30-day low.

    Expect: INSUFFICIENT_HISTORY. The engine must say this out loud. Returning
    no findings would be read as a clean bill of health.
    """
    start = BLACK_FRIDAY_2026 - timedelta(days=10)
    return (
        _steady("latestart.example", start, 10, "100.00")
        + _sale("latestart.example", BLACK_FRIDAY_2026, 4, "70.00", "100.00", "30")
    )


def window_gaming() -> list[Observation]:
    """A known blind spot, kept as a scenario so it stays visible.

    80 for 60 days, then lifted to 100 and held for 35 days, then 30% off 100.
    Because Art. 6a(2) sets 30 days as a floor rather than a fixed window, a
    trader who holds the inflated price for longer than 30 days satisfies the
    arithmetic exactly.

    Expect: no findings. The engine is right by the letter of the rule and the
    consumer is still misled. Detecting this needs a longer lookback, which is
    a judgement call rather than a legal one, so it belongs in a report's
    limitations section and not in a silent threshold change.
    """
    start = BLACK_FRIDAY_2026 - timedelta(days=95)
    return (
        _steady("slowburn.example", start, 60, "80.00")
        + _steady("slowburn.example", start + timedelta(days=60), 35, "100.00")
        + _sale("slowburn.example", BLACK_FRIDAY_2026, 4, "70.00", "100.00", "30")
    )


SCENARIOS = {
    "compliant": compliant,
    "mondpreis": mondpreis,
    "aldi-sued": aldi_sued,
    "missing-reference": missing_reference,
    "insufficient-history": insufficient_history,
    "window-gaming": window_gaming,
}


def all_observations() -> list[Observation]:
    """Every scenario at once, as a mixed corpus across retailers."""
    out: list[Observation] = []
    for build in SCENARIOS.values():
        out.extend(build())
    return out
