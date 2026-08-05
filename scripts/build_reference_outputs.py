from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CENT = Decimal("0.01")
TOLERANCE = Decimal("0.10")


def _money(value: str | int | Decimal) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def _date(value: str) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _as_float(value: Decimal) -> float:
    return float(f"{value:.2f}")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def build_reference_outputs(root: Path = ROOT) -> dict[str, dict[str, Any]]:
    """Build a specification oracle without importing application policy code."""
    input_paths = sorted((root / "input").glob("EC_*.json"))
    cases = [json.loads(path.read_text(encoding="utf-8")) for path in input_paths]
    order_ids = {case["customer_request"]["claimed_order_id"] for case in cases}

    orders = {
        row["order_id"]: row
        for row in _read_csv(root / "data" / "olist_orders_dataset.csv")
        if row["order_id"] in order_ids
    }
    items: dict[str, list[dict[str, str]]] = {}
    for row in _read_csv(root / "data" / "olist_order_items_dataset.csv"):
        if row["order_id"] in order_ids:
            items.setdefault(row["order_id"], []).append(row)
    payments: dict[str, list[dict[str, str]]] = {}
    for row in _read_csv(root / "data" / "olist_order_payments_dataset.csv"):
        if row["order_id"] in order_ids:
            payments.setdefault(row["order_id"], []).append(row)

    results: dict[str, dict[str, Any]] = {}
    for case in cases:
        case_id = case["case_id"]
        order_id = case["customer_request"]["claimed_order_id"]
        order = orders[order_id]
        order_items = sorted(items.get(order_id, []), key=lambda row: int(row["order_item_id"]))
        order_payments = sorted(
            payments.get(order_id, []), key=lambda row: int(row["payment_sequential"])
        )

        item_total = _money(sum((_money(row["price"]) for row in order_items), Decimal(0)))
        freight_total = _money(
            sum((_money(row["freight_value"]) for row in order_items), Decimal(0))
        )
        payment_total = _money(
            sum((_money(row["payment_value"]) for row in order_payments), Decimal(0))
        )
        payment_difference = _money(abs(payment_total - item_total - freight_total))

        carrier_date = _date(order["order_delivered_carrier_date"])
        customer_date = _date(order["order_delivered_customer_date"])
        estimated_date = _date(order["order_estimated_delivery_date"])
        if estimated_date is None:
            raise ValueError(f"Order {order_id} has no estimated delivery date")
        delivered_late = bool(customer_date and customer_date > estimated_date)
        delivered_within_estimate = bool(customer_date and customer_date <= estimated_date)
        late_items = [
            row
            for row in order_items
            if carrier_date and carrier_date > datetime.fromisoformat(row["shipping_limit_date"])
        ]

        status = order["order_status"]
        if status == "canceled" and payment_total > 0:
            issue, cause, action = (
                "canceled_order_paid",
                "ORDER_CANCELED_AFTER_PAYMENT",
                "issue_full_refund",
            )
            party_type, party_ids, refund = "platform", ["OLIST_PLATFORM"], payment_total
            evidence_types = ("item", "payment")
        elif status == "unavailable" and payment_total > 0:
            issue, cause, action = (
                "unavailable_order_paid",
                "ORDER_UNAVAILABLE_AFTER_PAYMENT",
                "issue_full_refund",
            )
            party_type, party_ids, refund = "platform", ["OLIST_PLATFORM"], payment_total
            evidence_types = ("payment",)
        elif delivered_late and late_items:
            issue, cause, action = (
                "late_delivery_seller",
                "SELLER_HANDOFF_AFTER_LIMIT",
                "refund_freight",
            )
            party_type = "seller"
            party_ids = sorted({row["seller_id"] for row in late_items})
            refund = freight_total
            evidence_types = ("item", "payment", "seller")
        elif delivered_late and order_items and carrier_date:
            issue, cause, action = (
                "late_delivery_logistics",
                "CARRIER_DELIVERED_AFTER_ESTIMATE",
                "refund_freight",
            )
            party_type, party_ids, refund = (
                "logistics_provider",
                ["LOGISTICS_PROVIDER"],
                freight_total,
            )
            evidence_types = ("item", "payment")
        elif len(order_payments) >= 2 and payment_difference <= TOLERANCE:
            issue, cause, action = (
                "valid_split_payment",
                "MULTIPLE_PAYMENTS_RECONCILED",
                "explain_valid_split_payment",
            )
            party_type, party_ids, refund = None, [], Decimal(0)
            evidence_types = ("item", "payment")
        elif delivered_within_estimate and payment_difference <= TOLERANCE:
            issue, cause, action = (
                "unsupported_late_claim",
                "DELIVERY_WITHIN_ESTIMATE",
                "reject_late_refund",
            )
            party_type, party_ids, refund = None, [], Decimal(0)
            evidence_types = ("item", "payment")
        else:
            raise ValueError(f"No EC_POLICY_V1 rule matched {case_id}/{order_id}")

        all_item_ids = [f'{order_id}:{row["order_item_id"]}' for row in order_items]
        all_payment_ids = [f'{order_id}:{row["payment_sequential"]}' for row in order_payments]
        item_ids = all_item_ids[:5]
        payment_ids = all_payment_ids[:5]
        seller_ids = sorted({row["seller_id"] for row in order_items})[:5]

        evidence = [f"order:{order_id}"]
        if "item" in evidence_types:
            evidence.extend(f"item:{entity_id}" for entity_id in all_item_ids)
        if "payment" in evidence_types:
            evidence.extend(f"payment:{entity_id}" for entity_id in all_payment_ids)
        if "seller" in evidence_types:
            evidence.extend(f"seller:{seller_id}" for seller_id in party_ids[:3])
        evidence = evidence[:9] + [f"policy:{cause}"]

        responsible_parties = []
        if party_type:
            responsible_parties = [
                {"party_type": party_type, "party_id": party_id}
                for party_id in party_ids[:3]
            ]

        results[case_id] = {
            "case_id": case_id,
            "assessment": {
                "primary_issue": issue,
                "case_status": "action_required" if refund > 0 else "no_action",
                "confidence": 1.0,
            },
            "affected_entities": {
                "order_ids": [order_id],
                "item_ids": item_ids,
                "seller_ids": seller_ids,
                "payment_ids": payment_ids,
            },
            "root_cause_analysis": {
                "ranked_causes": [{"cause_code": cause, "rank": 1}],
                "responsible_parties": responsible_parties,
            },
            "evidence_ids": evidence,
            "financial_resolution": {
                "currency": "BRL",
                "item_total_brl": _as_float(item_total),
                "freight_total_brl": _as_float(freight_total),
                "payment_total_brl": _as_float(payment_total),
                "recommended_refund_brl": _as_float(_money(refund)),
            },
            "resolution_actions": [action],
        }
    return results


def write_outputs(outputs: dict[str, dict[str, Any]], destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for old_path in destination.glob("EC_*.json"):
        old_path.unlink()
    for case_id, output in sorted(outputs.items()):
        (destination / f"{case_id}.json").write_text(
            json.dumps(output, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def compare_outputs(
    reference: dict[str, dict[str, Any]], candidate_dir: Path
) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    for case_id, expected in sorted(reference.items()):
        candidate_path = candidate_dir / f"{case_id}.json"
        if not candidate_path.exists():
            mismatches.append({"case_id": case_id, "field": "file", "actual": "missing"})
            continue
        actual = json.loads(candidate_path.read_text(encoding="utf-8"))
        for field in expected:
            if actual.get(field) != expected[field]:
                mismatches.append(
                    {
                        "case_id": case_id,
                        "field": field,
                        "expected": expected[field],
                        "actual": actual.get(field),
                    }
                )
    return mismatches


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an app-independent reference output set")
    parser.add_argument("--write", type=Path, help="Directory for the 50 reference JSON files")
    parser.add_argument("--compare", type=Path, help="Candidate output directory to compare")
    args = parser.parse_args()

    outputs = build_reference_outputs()
    summary: dict[str, Any] = {
        "reference_outputs": len(outputs),
        "issue_counts": dict(
            sorted(Counter(row["assessment"]["primary_issue"] for row in outputs.values()).items())
        ),
        "evidence_ids": sum(len(row["evidence_ids"]) for row in outputs.values()),
    }
    if args.write:
        write_outputs(outputs, args.write)
        summary["written_to"] = str(args.write.resolve())
    if args.compare:
        mismatches = compare_outputs(outputs, args.compare)
        summary["compared_to"] = str(args.compare.resolve())
        summary["field_mismatches"] = len(mismatches)
        summary["mismatch_details"] = mismatches
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
