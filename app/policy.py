from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from .config import PAYMENT_TOLERANCE_BRL, POLICY_VERSION
from .data_repository import CaseContext, money


@dataclass(frozen=True)
class Decision:
    primary_issue: str
    cause_code: str
    party_type: str | None
    party_ids: tuple[str, ...]
    refund: Decimal
    action: str


@dataclass(frozen=True)
class Rule:
    issue: str
    cause: str
    action: str
    matches: Callable[[CaseContext], bool]
    resolve_party: Callable[[CaseContext], tuple[str | None, tuple[str, ...]]]
    refund: Callable[[CaseContext], Decimal]

    def apply(self, context: CaseContext) -> Decision:
        party_type, party_ids = self.resolve_party(context)
        return Decision(
            primary_issue=self.issue,
            cause_code=self.cause,
            party_type=party_type,
            party_ids=party_ids,
            refund=money(self.refund(context)),
            action=self.action,
        )


def _no_party(_: CaseContext) -> tuple[None, tuple[str, ...]]:
    return None, ()


def _platform(_: CaseContext) -> tuple[str, tuple[str, ...]]:
    return "platform", ("OLIST_PLATFORM",)


def _logistics(_: CaseContext) -> tuple[str, tuple[str, ...]]:
    return "logistics_provider", ("LOGISTICS_PROVIDER",)


def _seller(context: CaseContext) -> tuple[str, tuple[str, ...]]:
    return "seller", context.late_seller_ids


ZERO = lambda _: Decimal("0")
PAYMENT = lambda context: context.payment_total
FREIGHT = lambda context: context.freight_total
TOLERANCE = Decimal(PAYMENT_TOLERANCE_BRL)


POLICY_RULES: dict[str, tuple[Rule, ...]] = {
    POLICY_VERSION: (
        Rule(
            "canceled_order_paid",
            "ORDER_CANCELED_AFTER_PAYMENT",
            "issue_full_refund",
            lambda c: c.order.status == "canceled" and c.payment_total > 0,
            _platform,
            PAYMENT,
        ),
        Rule(
            "unavailable_order_paid",
            "ORDER_UNAVAILABLE_AFTER_PAYMENT",
            "issue_full_refund",
            lambda c: c.order.status == "unavailable" and c.payment_total > 0,
            _platform,
            PAYMENT,
        ),
        Rule(
            "late_delivery_seller",
            "SELLER_HANDOFF_AFTER_LIMIT",
            "refund_freight",
            lambda c: c.delivered_after_estimate and bool(c.late_seller_ids),
            _seller,
            FREIGHT,
        ),
        Rule(
            "late_delivery_logistics",
            "CARRIER_DELIVERED_AFTER_ESTIMATE",
            "refund_freight",
            lambda c: (
                c.delivered_after_estimate
                and bool(c.items)
                and c.order.carrier_date is not None
                and not c.late_seller_ids
            ),
            _logistics,
            FREIGHT,
        ),
        Rule(
            "valid_split_payment",
            "MULTIPLE_PAYMENTS_RECONCILED",
            "explain_valid_split_payment",
            lambda c: len(c.payments) >= 2 and c.payment_difference <= TOLERANCE,
            _no_party,
            ZERO,
        ),
        Rule(
            "unsupported_late_claim",
            "DELIVERY_WITHIN_ESTIMATE",
            "reject_late_refund",
            lambda c: c.delivered_within_estimate and c.payment_difference <= TOLERANCE,
            _no_party,
            ZERO,
        ),
    )
}


class UnsupportedCaseError(RuntimeError):
    pass


def evaluate_policy(context: CaseContext) -> Decision:
    rules = POLICY_RULES.get(context.case.policy_version)
    if rules is None:
        raise UnsupportedCaseError(f"Unsupported policy version: {context.case.policy_version}")
    for rule in rules:
        if rule.matches(context):
            return rule.apply(context)
    raise UnsupportedCaseError(
        f"No {context.case.policy_version} rule matched order {context.order.order_id}"
    )

