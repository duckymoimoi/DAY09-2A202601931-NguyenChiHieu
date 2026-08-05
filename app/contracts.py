from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CustomerRequest(StrictModel):
    language: str
    message: str
    claimed_order_id: str = Field(min_length=1)


class InputCase(StrictModel):
    case_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    opened_at: datetime
    customer_request: CustomerRequest
    policy_version: str


class Assessment(StrictModel):
    primary_issue: str
    case_status: Literal["action_required", "no_action"]
    confidence: float = Field(ge=0, le=1)


class AffectedEntities(StrictModel):
    order_ids: list[str] = Field(max_length=5)
    item_ids: list[str] = Field(max_length=5)
    seller_ids: list[str] = Field(max_length=5)
    payment_ids: list[str] = Field(max_length=5)


class RankedCause(StrictModel):
    cause_code: str
    rank: int = Field(ge=1, le=3)


class ResponsibleParty(StrictModel):
    party_type: str
    party_id: str


class RootCauseAnalysis(StrictModel):
    ranked_causes: list[RankedCause] = Field(max_length=3)
    responsible_parties: list[ResponsibleParty] = Field(max_length=3)


class FinancialResolution(StrictModel):
    currency: Literal["BRL"] = "BRL"
    item_total_brl: float = Field(ge=0)
    freight_total_brl: float = Field(ge=0)
    payment_total_brl: float = Field(ge=0)
    recommended_refund_brl: float = Field(ge=0)


class CaseOutput(StrictModel):
    case_id: str
    assessment: Assessment
    affected_entities: AffectedEntities
    root_cause_analysis: RootCauseAnalysis
    evidence_ids: list[str] = Field(max_length=10)
    financial_resolution: FinancialResolution
    resolution_actions: list[str] = Field(max_length=5)

    @field_validator("evidence_ids")
    @classmethod
    def evidence_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("evidence_ids must be unique")
        return value


class OrderFacts(StrictModel):
    order_id: str
    order_status: str
    item_ids: list[str]
    seller_ids: list[str]
    late_seller_ids: list[str]


class PaymentFacts(StrictModel):
    payment_ids: list[str]
    item_total: Decimal
    freight_total: Decimal
    payment_total: Decimal
    difference: Decimal
    reconciled: bool


class DeliveryFacts(StrictModel):
    delivered_to_customer: bool
    delivered_after_estimate: bool
    carrier_handoff_known: bool


class InvestigationBundle(StrictModel):
    case_id: str
    order: OrderFacts
    payment: PaymentFacts
    delivery: DeliveryFacts

