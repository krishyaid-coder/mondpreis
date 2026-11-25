"""Command line for the compliance engine.

The engine stays a pure function. This module only loads observations and
prints what `analyze` returns.

    mondpreis scenarios                 # the built-in histories
    mondpreis scenarios mondpreis       # one scenario by name
    mondpreis check observations.json   # a file of observations
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .models import Finding, Observation, Severity
from .omnibus import analyze
from .synthetic import SCENARIOS, all_observations


def _money(value: object, field: str) -> Decimal:
    """Prices arrive as strings so JSON numbers cannot sneak in as floats."""
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string, for example \"19.99\"")
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{field} is not a decimal: {value!r}") from exc


def _optional_money(value: object, field: str) -> Decimal | None:
    if value is None:
        return None
    return _money(value, field)


def observation_from_obj(raw: object) -> Observation:
    if not isinstance(raw, dict):
        raise ValueError("each observation must be a JSON object")
    required = ("product_id", "retailer", "observed_on", "price")
    missing = [key for key in required if key not in raw]
    if missing:
        raise ValueError(f"observation missing {', '.join(missing)}")
    try:
        observed_on = date.fromisoformat(raw["observed_on"])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"observed_on must be YYYY-MM-DD, got {raw['observed_on']!r}") from exc
    return Observation(
        product_id=str(raw["product_id"]),
        retailer=str(raw["retailer"]),
        observed_on=observed_on,
        price=_money(raw["price"], "price"),
        currency=str(raw.get("currency", "EUR")),
        reference_price=_optional_money(raw.get("reference_price"), "reference_price"),
        advertised_discount_pct=_optional_money(
            raw.get("advertised_discount_pct"), "advertised_discount_pct"
        ),
    )


def load_observations(path: Path) -> list[Observation]:
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON list of observations")
    return [observation_from_obj(item) for item in data]


def finding_to_dict(finding: Finding) -> dict[str, object]:
    return {
        "code": finding.code.value,
        "severity": finding.severity.value,
        "product_id": finding.product_id,
        "retailer": finding.retailer,
        "sale_start": finding.sale_start.isoformat(),
        "message": finding.message,
        "evidence": finding.evidence,
    }


def render_text(findings: list[Finding]) -> str:
    if not findings:
        return "No findings.\n"
    lines: list[str] = []
    for finding in findings:
        lines.append(
            f"{finding.severity.value:7} {finding.code.value:24} "
            f"{finding.retailer}  {finding.product_id}  {finding.sale_start.isoformat()}"
        )
        lines.append(f"        {finding.message}")
    errors = sum(f.severity is Severity.ERROR for f in findings)
    warnings = sum(f.severity is Severity.WARNING for f in findings)
    infos = sum(f.severity is Severity.INFO for f in findings)
    lines.append(f"{len(findings)} findings: {errors} error, {warnings} warning, {infos} info")
    return "\n".join(lines) + "\n"


def _emit(findings: list[Finding], as_json: bool, stream: object) -> int:
    text = (
        json.dumps([finding_to_dict(f) for f in findings], indent=2) + "\n"
        if as_json
        else render_text(findings)
    )
    stream.write(text)  # type: ignore[attr-defined]
    return 1 if any(f.severity is Severity.ERROR for f in findings) else 0


def _scenarios(names: list[str]) -> list[Observation]:
    unknown = [name for name in names if name not in SCENARIOS]
    if unknown:
        known = ", ".join(sorted(SCENARIOS))
        raise ValueError(f"unknown scenario: {', '.join(unknown)}. Known: {known}")
    if not names:
        return all_observations()
    observations: list[Observation] = []
    for name in names:
        observations.extend(SCENARIOS[name]())
    return observations


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mondpreis",
        description="Verify advertised price reductions against observed price history.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    scenarios = sub.add_parser("scenarios", help="evaluate the built-in synthetic histories")
    scenarios.add_argument("names", nargs="*", help="scenario names; default is all of them")
    scenarios.add_argument("--json", action="store_true", help="print findings as JSON")

    check = sub.add_parser("check", help="evaluate a JSON file of observations")
    check.add_argument("path", type=Path)
    check.add_argument("--json", action="store_true", help="print findings as JSON")
    return parser


def main(argv: list[str] | None = None, stream: object | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    out = stream if stream is not None else sys.stdout
    try:
        if args.command == "scenarios":
            observations = _scenarios(args.names)
        else:
            observations = load_observations(args.path)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return _emit(analyze(observations), args.json, out)
