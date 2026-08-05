from __future__ import annotations

from decimal import Decimal

from .contracts import (
    AffectedEntities,
    Assessment,
    CaseOutput,
    DeliveryFacts,
    FinancialResolution,
    InvestigationBundle,
    OrderFacts,
    PaymentFacts,
    RankedCause,
    ResponsibleParty,
    RootCauseAnalysis,
)
from .config import DEFAULT_CONFIDENCE
from .data_repository import CaseContext
from .policy import Decision, TOLERANCE, evaluate_policy


def _as_float(value: Decimal) -> float:
    return float(f"{value:.2f}")


EVIDENCE_TYPES_BY_CAUSE: dict[str, tuple[str, ...]] = {
    "ORDER_CANCELED_AFTER_PAYMENT": ("payment",),
    "ORDER_UNAVAILABLE_AFTER_PAYMENT": ("payment",),
    "SELLER_HANDOFF_AFTER_LIMIT": ("item", "seller"),
    "CARRIER_DELIVERED_AFTER_ESTIMATE": ("item",),
    "MULTIPLE_PAYMENTS_RECONCILED": ("item", "payment"),
    "DELIVERY_WITHIN_ESTIMATE": ("item", "payment"),
}


def _build_evidence(context: CaseContext, decision: Decision) -> list[str]:
    """Return the smallest auditable evidence set for the matched policy rule."""
    evidence = [f"order:{context.order.order_id}"]
    evidence_types = EVIDENCE_TYPES_BY_CAUSE[decision.cause_code]

    if "item" in evidence_types:
        evidence.extend(f"item:{row.entity_id}" for row in context.items)
    if "payment" in evidence_types:
        evidence.extend(f"payment:{row.entity_id}" for row in context.payments)
    if "seller" in evidence_types:
        evidence.extend(f"seller:{seller_id}" for seller_id in decision.party_ids)

    # Keep policy evidence even when a large order exceeds the schema's 10-ID cap.
    return evidence[:9] + [f"policy:{decision.cause_code}"]


class OrderSellerAgent:
    name = "order_seller_agent"

    def investigate(self, context: CaseContext) -> OrderFacts:
        return OrderFacts(
            order_id=context.order.order_id,
            order_status=context.order.status,
            item_ids=[row.entity_id for row in context.items],
            seller_ids=list(context.seller_ids),
            late_seller_ids=list(context.late_seller_ids),
        )


class PaymentAgent:
    name = "payment_agent"

    def investigate(self, context: CaseContext) -> PaymentFacts:
        return PaymentFacts(
            payment_ids=[row.entity_id for row in context.payments],
            item_total=context.item_total,
            freight_total=context.freight_total,
            payment_total=context.payment_total,
            difference=context.payment_difference,
            reconciled=context.payment_difference <= TOLERANCE,
        )


class DeliveryAgent:
    name = "delivery_agent"

    def investigate(self, context: CaseContext) -> DeliveryFacts:
        return DeliveryFacts(
            delivered_to_customer=context.order.customer_date is not None,
            delivered_after_estimate=context.delivered_after_estimate,
            carrier_handoff_known=context.order.carrier_date is not None,
        )


class PolicyAgent:
    name = "policy_agent"

    def decide(self, context: CaseContext, bundle: InvestigationBundle) -> tuple[Decision, CaseOutput]:
        # The typed bundle is deliberately required: PolicyAgent cannot bypass handoffs.
        if bundle.case_id != context.case.case_id:
            raise ValueError("Investigation bundle belongs to another case")
        decision = evaluate_policy(context)

        orders = [context.order.order_id]
        items = [row.entity_id for row in context.items][:5]
        sellers = list(context.seller_ids)[:5]
        payments = [row.entity_id for row in context.payments][:5]

        evidence = _build_evidence(context, decision)

        parties = []
        if decision.party_type:
            parties = [
                ResponsibleParty(party_type=decision.party_type, party_id=party_id)
                for party_id in decision.party_ids[:3]
            ]

        output = CaseOutput(
            case_id=context.case.case_id,
            assessment=Assessment(
                primary_issue=decision.primary_issue,
                case_status="action_required" if decision.refund > 0 else "no_action",
                confidence=DEFAULT_CONFIDENCE,
            ),
            affected_entities=AffectedEntities(
                order_ids=orders,
                item_ids=items,
                seller_ids=sellers,
                payment_ids=payments,
            ),
            root_cause_analysis=RootCauseAnalysis(
                ranked_causes=[RankedCause(cause_code=decision.cause_code, rank=1)],
                responsible_parties=parties,
            ),
            evidence_ids=evidence,
            financial_resolution=FinancialResolution(
                item_total_brl=_as_float(context.item_total),
                freight_total_brl=_as_float(context.freight_total),
                payment_total_brl=_as_float(context.payment_total),
                recommended_refund_brl=_as_float(decision.refund),
            ),
            resolution_actions=[decision.action],
        )
        return decision, output


class VerifierAgent:
    name = "verifier_agent"

    def verify(self, context: CaseContext, output: CaseOutput) -> list[str]:
        errors: list[str] = []
        expected = evaluate_policy(context)
        if output.case_id != context.case.case_id:
            errors.append("case_id mismatch")
        if output.assessment.primary_issue != expected.primary_issue:
            errors.append("primary issue does not match policy")
        expected_status = "action_required" if expected.refund > 0 else "no_action"
        if output.assessment.case_status != expected_status:
            errors.append("case status does not match refund")

        financial = output.financial_resolution
        expected_money = (
            _as_float(context.item_total),
            _as_float(context.freight_total),
            _as_float(context.payment_total),
            _as_float(expected.refund),
        )
        actual_money = (
            financial.item_total_brl,
            financial.freight_total_brl,
            financial.payment_total_brl,
            financial.recommended_refund_brl,
        )
        if actual_money != expected_money:
            errors.append(f"financial mismatch: {actual_money} != {expected_money}")

        valid_evidence = {f"order:{context.order.order_id}", f"policy:{expected.cause_code}"}
        valid_evidence.update(f"item:{row.entity_id}" for row in context.items)
        valid_evidence.update(f"payment:{row.entity_id}" for row in context.payments)
        valid_evidence.update(f"seller:{seller_id}" for seller_id in context.seller_ids)
        invalid = set(output.evidence_ids) - valid_evidence
        if invalid:
            errors.append(f"invalid evidence IDs: {sorted(invalid)}")

        expected_evidence = set(_build_evidence(context, expected))
        actual_evidence = set(output.evidence_ids)
        if actual_evidence != expected_evidence:
            missing = sorted(expected_evidence - actual_evidence)
            irrelevant = sorted(actual_evidence - expected_evidence)
            errors.append(
                f"evidence relevance mismatch: missing={missing}, irrelevant={irrelevant}"
            )

        if f"policy:{expected.cause_code}" not in output.evidence_ids:
            errors.append("missing policy evidence")
        if expected.action not in output.resolution_actions:
            errors.append("missing resolution action")
        if not context.items:
            if output.affected_entities.item_ids or output.affected_entities.seller_ids:
                errors.append("item/seller entities must be empty without item rows")
            if financial.item_total_brl != 0 or financial.freight_total_brl != 0:
                errors.append("item/freight totals must be zero without item rows")
        for seller_id in output.affected_entities.seller_ids:
            if seller_id not in context.known_seller_ids:
                errors.append(f"unknown seller ID: {seller_id}")
        return errors
