from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from mondpreis import synthetic
from mondpreis.models import Code, Severity
from mondpreis.omnibus import analyze, find_episodes
from mondpreis.synthetic import BLACK_FRIDAY_2026


def _codes(observations) -> set[Code]:
    return {f.code for f in analyze(observations)}


# ── the scenarios are the specification ───────────────────────────────


def test_compliant_sale_produces_nothing():
    assert analyze(synthetic.compliant()) == []


def test_mondpreis_is_caught_three_ways():
    codes = _codes(synthetic.mondpreis())
    assert codes == {
        Code.REFERENCE_ABOVE_LOW,
        Code.PERCENT_OVERSTATED,
        Code.SHORT_LIVED_REFERENCE,
    }


def test_aldi_sued_pattern_matches_the_ruling():
    """C-330/23. Citing an older higher price and computing the percentage
    from it breaches Art. 6a(2) twice over."""
    codes = _codes(synthetic.aldi_sued())
    assert codes == {Code.REFERENCE_ABOVE_LOW, Code.PERCENT_OVERSTATED}


def test_missing_reference_fires_alone():
    """The arithmetic in this scenario is honest, so only Art. 6a(1) is
    breached. If anything else fires, a check is leaking."""
    codes = _codes(synthetic.missing_reference())
    assert codes == {Code.MISSING_REFERENCE}


def test_short_history_is_reported_not_passed():
    findings = analyze(synthetic.insufficient_history())
    assert [f.code for f in findings] == [Code.INSUFFICIENT_HISTORY]
    assert findings[0].severity is Severity.INFO


def test_window_gaming_is_a_documented_blind_spot():
    """Holding an inflated price for longer than 30 days satisfies the rule.
    The engine reports nothing, which is correct and also the reason this
    needs stating in any report's limitations."""
    assert analyze(synthetic.window_gaming()) == []


# ── the trap this engine exists to avoid ──────────────────────────────


def test_long_sale_cannot_vouch_for_itself():
    """Regression guard for the central modelling error.

    A naive implementation takes the 30-day lookback from the day being
    examined. By day three of a sale the reduced price is itself inside the
    window, becomes the low, and the violation disappears. Anchoring to the
    episode start is what prevents that, so a 40-day sale must stay flagged
    for its whole length.
    """
    obs = synthetic.mondpreis()
    long_sale = [o for o in obs if not o.claims_discount]
    sale_day = next(o for o in obs if o.claims_discount)
    for i in range(40):
        long_sale.append(
            type(sale_day)(
                product_id=sale_day.product_id,
                retailer=sale_day.retailer,
                observed_on=BLACK_FRIDAY_2026 + timedelta(days=i),
                price=sale_day.price,
                reference_price=sale_day.reference_price,
                advertised_discount_pct=sale_day.advertised_discount_pct,
            )
        )
    findings = analyze(long_sale)
    assert Code.REFERENCE_ABOVE_LOW in {f.code for f in findings}
    # One episode, so one finding of each kind, not one per sale day.
    assert sum(f.code is Code.REFERENCE_ABOVE_LOW for f in findings) == 1


def test_window_excludes_the_sale_day_itself():
    """If the sale day leaked into its own lookback the low would equal the
    sale price and nothing would ever fire."""
    findings = analyze(synthetic.aldi_sued())
    ref = next(f for f in findings if f.code is Code.REFERENCE_ABOVE_LOW)
    assert ref.evidence["observed_low"] == "80.00"


# ── episode detection ─────────────────────────────────────────────────


def test_a_missed_collection_day_does_not_split_a_sale():
    obs = [o for o in synthetic.compliant() if o.observed_on != BLACK_FRIDAY_2026 + timedelta(days=1)]
    sale = [o for o in obs if o.claims_discount]
    assert len(find_episodes(sorted(sale, key=lambda o: o.observed_on))) == 1


def test_a_long_outage_does_split_a_sale():
    sale = sorted(
        (o for o in synthetic.compliant() if o.claims_discount),
        key=lambda o: o.observed_on,
    )
    gapped = [sale[0]] + [
        type(sale[0])(
            product_id=o.product_id,
            retailer=o.retailer,
            observed_on=o.observed_on + timedelta(days=30),
            price=o.price,
            reference_price=o.reference_price,
            advertised_discount_pct=o.advertised_discount_pct,
        )
        for o in sale[1:]
    ]
    assert len(find_episodes(gapped)) == 2


def test_price_without_a_claim_is_not_an_episode():
    assert find_episodes([o for o in synthetic.compliant() if not o.claims_discount]) == []


# ── arithmetic ────────────────────────────────────────────────────────


def test_rounding_tolerance_absorbs_an_honest_retailer():
    """A retailer advertising -30% off a true 29.6% reduction is rounding,
    not lying. Without tolerance this would be a false positive."""
    start = BLACK_FRIDAY_2026 - timedelta(days=40)
    obs = synthetic._steady("rounder.example", start, 40, "99.00") + synthetic._sale(
        "rounder.example", BLACK_FRIDAY_2026, 2, "69.70", "99.00", "30"
    )
    assert analyze(obs) == []


def test_percentages_use_decimal_not_float():
    """0.1 + 0.2 arithmetic in money would make findings wrong by a cent."""
    findings = analyze(synthetic.aldi_sued())
    pct = next(f for f in findings if f.code is Code.PERCENT_OVERSTATED)
    assert pct.evidence["actual_pct"] == "12.5"
    assert isinstance(Decimal(pct.evidence["observed_low"]), Decimal)


def test_mixed_corpus_separates_retailers():
    findings = analyze(synthetic.all_observations())
    retailers = {f.retailer for f in findings}
    assert "cleanshop.example" not in retailers
    assert "slowburn.example" not in retailers
    assert "moonshop.example" in retailers
