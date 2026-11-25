"""Domain types for price observations and compliance findings.

Money is `Decimal` throughout, never `float`. A float cannot hold 19.99
exactly, and the engine's whole job is comparing prices and deriving
percentages from them. Float drift here would produce findings that are wrong
by a cent, which is indistinguishable from a bug in the legal logic.

Dates are `date`, not `datetime`. The rule is expressed in days ("the lowest
price applied during the 30 days prior"), so a day is the natural unit and
timezone handling is a problem we do not need to have.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum


class Severity(str, Enum):
    ERROR = "error"      # a plain breach of the stated rule
    WARNING = "warning"  # evidence of the behaviour the rule exists to stop
    INFO = "info"        # we cannot evaluate, and say so rather than passing


class Code(str, Enum):
    """Finding codes, each tied to the provision it tests."""

    # Art. 6a(1) 98/6/EC: an announced reduction must indicate the prior price.
    MISSING_REFERENCE = "missing-reference"
    # Art. 6a(2): the prior price is the LOWEST in the preceding 30 days.
    REFERENCE_ABOVE_LOW = "reference-above-low"
    # CJEU C-330/23 (Aldi Süd): the percentage must be computed from that low.
    PERCENT_OVERSTATED = "percent-overstated"
    # The misleading-practice test: a reference held for an unreasonably short
    # time. Not a per se breach, so this is evidence rather than a verdict.
    SHORT_LIVED_REFERENCE = "short-lived-reference"
    # Fewer than 30 days of history. Silence would read as compliance.
    INSUFFICIENT_HISTORY = "insufficient-history"


@dataclass(frozen=True)
class Observation:
    """What one product page showed on one day.

    `reference_price` and `advertised_discount_pct` are what the page claimed,
    not anything we computed. Keeping the claim separate from our own
    arithmetic is what makes a finding defensible: we can always show the
    retailer's own numbers next to the history they contradict.
    """

    product_id: str
    retailer: str
    observed_on: date
    price: Decimal
    currency: str = "EUR"
    # Struck-through price shown next to the current one, if any.
    reference_price: Decimal | None = None
    # Advertised reduction, e.g. Decimal("30") for "-30%".
    advertised_discount_pct: Decimal | None = None

    @property
    def claims_discount(self) -> bool:
        """Whether the page announced a reduction at all.

        Either a struck-through price or a percentage counts as an
        announcement, since Art. 6a is triggered by the announcement rather
        than by any particular way of rendering it.
        """
        return self.reference_price is not None or self.advertised_discount_pct is not None


@dataclass(frozen=True)
class Finding:
    code: Code
    severity: Severity
    product_id: str
    retailer: str
    # The day the sale began, which is the day the rule is tested against.
    sale_start: date
    message: str
    # Everything needed to reproduce the arithmetic, for the report appendix.
    evidence: dict[str, str]


@dataclass(frozen=True)
class Episode:
    """A consecutive run of days on which a discount was advertised.

    This exists because of a trap. Once a sale price lands in the history, a
    naive 30-day lookback taken on day three of the sale finds the sale price
    itself as the low, and every ongoing sale starts looking compliant. The
    rule tests the price "prior to the application of the price reduction", so
    the window must be anchored to the day the sale STARTED, not to each day
    inside it.
    """

    product_id: str
    retailer: str
    start: date
    end: date
    observations: tuple[Observation, ...]

    @property
    def first(self) -> Observation:
        return self.observations[0]
