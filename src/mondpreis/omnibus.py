"""The compliance engine.

Tests advertised price reductions against observed price history, following
Directive 98/6/EC Art. 6a as amended by the Omnibus Directive (EU) 2019/2161,
and as construed by the CJEU in C-330/23 (Aldi Süd, 26 September 2024).

The engine is a pure function over a list of observations. It performs no
collection and no I/O, which is what makes it testable against constructed
scenarios rather than against whatever the internet happened to be doing.

Not legal advice. A finding here means "this contradicts the retailer's own
displayed numbers", which is a factual claim. Whether it is an infringement is
for a regulator or a court.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from .models import Code, Episode, Finding, Observation, Severity

# Art. 6a(2) sets 30 days as the MINIMUM lookback. Longer is permitted, which
# is itself a gaming surface (see SHORT_LIVED_REFERENCE).
LOOKBACK_DAYS = 30

# Retailers round their advertised percentages. Without a tolerance the engine
# would flag "-30%" when the true figure is 29.6%, which is noise, not fraud.
PERCENT_TOLERANCE = Decimal("1.0")

# Days of missing collection we will bridge before treating a sale as ended.
# A collector that misses Sunday should not split one sale into two episodes.
EPISODE_GAP_DAYS = 3

# How much of the 30-day window must actually be observed before we are
# willing to name a low. Below this we report INSUFFICIENT_HISTORY instead of
# quietly passing the claim, which would be the dishonest failure mode.
MIN_WINDOW_COVERAGE = 20

# A reference price in effect for no longer than this immediately before the
# sale, where cheaper prices exist further back, is the Mondpreis shape.
SHORT_LIVED_DAYS = 7


def _group(observations: list[Observation]) -> dict[tuple[str, str], list[Observation]]:
    series: dict[tuple[str, str], list[Observation]] = defaultdict(list)
    for obs in observations:
        series[(obs.product_id, obs.retailer)].append(obs)
    for key in series:
        series[key].sort(key=lambda o: o.observed_on)
    return dict(series)


def find_episodes(series: list[Observation], gap_days: int = EPISODE_GAP_DAYS) -> list[Episode]:
    """Split one product's history into runs of consecutive discount days.

    An episode ends when the page stops advertising a reduction, or when the
    gap in observations grows large enough that we cannot claim the sale was
    continuous.
    """
    episodes: list[Episode] = []
    current: list[Observation] = []

    def flush() -> None:
        if current:
            episodes.append(
                Episode(
                    product_id=current[0].product_id,
                    retailer=current[0].retailer,
                    start=current[0].observed_on,
                    end=current[-1].observed_on,
                    observations=tuple(current),
                )
            )
            current.clear()

    for obs in series:
        if not obs.claims_discount:
            flush()
            continue
        if current and (obs.observed_on - current[-1].observed_on).days > gap_days:
            flush()
        current.append(obs)
    flush()
    return episodes


def _window(series: list[Observation], sale_start: date, lookback: int) -> list[Observation]:
    """Observations in [sale_start - lookback, sale_start).

    The sale day is excluded on purpose. Art. 6a asks for the price prior to
    the application of the reduction, so including the reduced price itself
    would let every sale vouch for its own legality.
    """
    first_day = sale_start - timedelta(days=lookback)
    return [o for o in series if first_day <= o.observed_on < sale_start]


def _run_length_at_or_above(
    window: list[Observation], sale_start: date, level: Decimal
) -> int:
    """Length of the unbroken run of days ending at the sale during which the
    price sat at or above `level`."""
    run = 0
    for obs in reversed(window):
        if obs.price >= level:
            run += 1
        else:
            break
    return run


def check_episode(
    episode: Episode,
    series: list[Observation],
    lookback: int = LOOKBACK_DAYS,
    percent_tolerance: Decimal = PERCENT_TOLERANCE,
    min_coverage: int = MIN_WINDOW_COVERAGE,
    short_lived_days: int = SHORT_LIVED_DAYS,
) -> list[Finding]:
    """Evaluate one discount episode against the history preceding it."""
    claim = episode.first
    window = _window(series, episode.start, lookback)
    findings: list[Finding] = []

    def finding(code: Code, severity: Severity, message: str, **evidence: object) -> Finding:
        return Finding(
            code=code,
            severity=severity,
            product_id=episode.product_id,
            retailer=episode.retailer,
            sale_start=episode.start,
            message=message,
            evidence={k: str(v) for k, v in evidence.items()},
        )

    # Can we evaluate at all? Two ways to fail: the history does not reach
    # back far enough, or it reaches back but is too sparse to trust.
    earliest = series[0].observed_on if series else episode.start
    reaches_back = earliest <= episode.start - timedelta(days=lookback)
    if not reaches_back or len(window) < min_coverage:
        return [
            finding(
                Code.INSUFFICIENT_HISTORY,
                Severity.INFO,
                f"Only {len(window)} observed days in the {lookback} days before "
                f"the sale, so the reference price cannot be verified.",
                observed_days=len(window),
                required_days=min_coverage,
                history_starts=earliest,
                window_starts=episode.start - timedelta(days=lookback),
            )
        ]

    low = min(o.price for o in window)
    low_on = min((o for o in window if o.price == low), key=lambda o: o.observed_on).observed_on

    # Art. 6a(1): announcing a reduction obliges the trader to state the prior
    # price. A bare percentage does not satisfy that.
    if claim.advertised_discount_pct is not None and claim.reference_price is None:
        findings.append(
            finding(
                Code.MISSING_REFERENCE,
                Severity.ERROR,
                f"Advertised -{claim.advertised_discount_pct}% without showing any "
                f"prior price. The 30-day low was {low} on {low_on}.",
                advertised_pct=claim.advertised_discount_pct,
                observed_low=low,
                observed_low_on=low_on,
            )
        )

    # Art. 6a(2): the stated prior price must be the lowest in the window.
    if claim.reference_price is not None and claim.reference_price > low:
        overstatement = claim.reference_price - low
        findings.append(
            finding(
                Code.REFERENCE_ABOVE_LOW,
                Severity.ERROR,
                f"Shown prior price {claim.reference_price} exceeds the observed "
                f"{lookback}-day low of {low} (on {low_on}) by {overstatement}.",
                shown_reference=claim.reference_price,
                observed_low=low,
                observed_low_on=low_on,
                overstatement=overstatement,
            )
        )

    # C-330/23: the advertised percentage must be derived from that same low.
    if claim.advertised_discount_pct is not None and low > 0:
        true_pct = (low - claim.price) / low * Decimal(100)
        if claim.advertised_discount_pct > true_pct + percent_tolerance:
            findings.append(
                finding(
                    Code.PERCENT_OVERSTATED,
                    Severity.ERROR,
                    f"Advertised -{claim.advertised_discount_pct}% but the reduction "
                    f"from the {lookback}-day low of {low} is "
                    f"{true_pct.quantize(Decimal('0.1'))}%.",
                    advertised_pct=claim.advertised_discount_pct,
                    actual_pct=true_pct.quantize(Decimal("0.1")),
                    sale_price=claim.price,
                    observed_low=low,
                )
            )

    # The misleading-practice test. A prior price only briefly in effect, with
    # cheaper prices behind it, is the behaviour the rule was written to stop.
    # Separate from the checks above because it explains HOW, and because a
    # trader can satisfy the 30-day arithmetic and still do this by exploiting
    # the fact that 30 days is a floor rather than a fixed window.
    if claim.reference_price is not None:
        run = _run_length_at_or_above(window, episode.start, claim.reference_price)
        cheaper_before = [o for o in series if o.observed_on < episode.start and o.price < claim.reference_price]
        if 0 < run <= short_lived_days and cheaper_before:
            findings.append(
                finding(
                    Code.SHORT_LIVED_REFERENCE,
                    Severity.WARNING,
                    f"Prior price {claim.reference_price} was in effect for only "
                    f"{run} day(s) before the sale, while cheaper prices appear "
                    f"earlier in the history.",
                    shown_reference=claim.reference_price,
                    days_at_reference=run,
                    cheapest_before=min(o.price for o in cheaper_before),
                )
            )

    return findings


def analyze(observations: list[Observation], **kwargs: object) -> list[Finding]:
    """Check every discount episode in a set of observations.

    Observations may cover many products and retailers in any order.
    """
    findings: list[Finding] = []
    for series in _group(observations).values():
        for episode in find_episodes(series):
            findings.extend(check_episode(episode, series, **kwargs))  # type: ignore[arg-type]
    findings.sort(key=lambda f: (f.retailer, f.product_id, f.sale_start, f.code.value))
    return findings
