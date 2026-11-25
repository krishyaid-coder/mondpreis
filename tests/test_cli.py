from __future__ import annotations

import json
from io import StringIO

from mondpreis.cli import main


def test_compliant_scenario_exits_clean():
    out = StringIO()
    code = main(["scenarios", "compliant"], stream=out)
    assert code == 0
    assert "No findings." in out.getvalue()


def test_aldi_scenario_exits_with_errors():
    out = StringIO()
    code = main(["scenarios", "aldi-sued", "--json"], stream=out)
    assert code == 1
    findings = json.loads(out.getvalue())
    codes = {item["code"] for item in findings}
    assert codes == {"reference-above-low", "percent-overstated"}


def test_check_reads_a_json_file(tmp_path):
    path = tmp_path / "obs.json"
    path.write_text(
        json.dumps(
            [
                {
                    "product_id": "kettle",
                    "retailer": "shop.example",
                    "observed_on": "2026-10-01",
                    "price": "50.00",
                },
                {
                    "product_id": "kettle",
                    "retailer": "shop.example",
                    "observed_on": "2026-11-27",
                    "price": "40.00",
                    "reference_price": "50.00",
                    "advertised_discount_pct": "20",
                },
            ]
        )
    )
    out = StringIO()
    code = main(["check", str(path)], stream=out)
    assert code == 0
    assert "insufficient-history" in out.getvalue()


def test_numeric_prices_are_rejected(tmp_path):
    path = tmp_path / "obs.json"
    path.write_text(
        json.dumps(
            [
                {
                    "product_id": "kettle",
                    "retailer": "shop.example",
                    "observed_on": "2026-11-27",
                    "price": 19.99,
                }
            ]
        )
    )
    code = main(["check", str(path)], stream=StringIO())
    assert code == 2


def test_unknown_scenario_is_an_error():
    assert main(["scenarios", "nope"], stream=StringIO()) == 2
