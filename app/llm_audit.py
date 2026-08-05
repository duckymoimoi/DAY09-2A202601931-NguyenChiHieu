from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from groq import AuthenticationError, Groq, RateLimitError

from .config import MODEL_ID, Settings
from .contracts import InvestigationBundle


@dataclass(frozen=True)
class AuditResult:
    attempted: bool
    succeeded: bool
    agreed: bool | None
    key_slot: int | None
    prompt_tokens: int
    completion_tokens: int
    response: dict[str, Any]
    error: str | None = None


class GroqPolicyAuditAgent:
    """Non-authoritative LLM reviewer; deterministic policy remains the source of truth."""

    name = "groq_policy_audit_agent"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._last_request_at = 0.0
        self._minimum_interval_seconds = 1.2

    def _sdk_base_url(self) -> str:
        # The OpenAI-compatible URL commonly ends in /openai/v1, while the
        # Groq SDK adds that route itself.
        suffix = "/openai/v1"
        base_url = self.settings.base_url.rstrip("/")
        return base_url[: -len(suffix)] if base_url.endswith(suffix) else base_url

    def audit(self, bundle: InvestigationBundle, selected_issue: str) -> AuditResult:
        if not self.settings.llm_audit or not self.settings.api_keys:
            return AuditResult(False, False, None, None, 0, 0, {}, "disabled or no API key")

        rule_checks = [
            (
                "canceled_order_paid",
                bundle.order.order_status == "canceled" and bundle.payment.payment_total > 0,
            ),
            (
                "unavailable_order_paid",
                bundle.order.order_status == "unavailable" and bundle.payment.payment_total > 0,
            ),
            (
                "late_delivery_seller",
                bundle.delivery.delivered_after_estimate and bool(bundle.order.late_seller_ids),
            ),
            (
                "late_delivery_logistics",
                bundle.delivery.delivered_after_estimate
                and bool(bundle.order.item_ids)
                and bundle.delivery.carrier_handoff_known
                and not bundle.order.late_seller_ids,
            ),
            (
                "valid_split_payment",
                len(bundle.payment.payment_ids) >= 2 and bundle.payment.reconciled,
            ),
            (
                "unsupported_late_claim",
                bundle.delivery.delivered_to_customer
                and not bundle.delivery.delivered_after_estimate
                and bundle.payment.reconciled,
            ),
        ]
        matching_rules = [name for name, matched in rule_checks if matched]
        expected_issue = matching_rules[0] if matching_rules else None
        prompt = (
            "Compare two strings. Reply as JSON only with keys "
            '"agreed" (boolean) and "reason" (short string). Set agreed=true exactly '
            "when selected_issue equals expected_issue. "
            f"selected_issue={json.dumps(selected_issue)}; expected_issue={json.dumps(expected_issue)}."
        )

        last_error: str | None = None
        for slot, key in enumerate(self.settings.api_keys, start=1):
            try:
                delay = self._minimum_interval_seconds - (time.monotonic() - self._last_request_at)
                if delay > 0:
                    time.sleep(delay)
                client = Groq(api_key=key, base_url=self._sdk_base_url())
                try:
                    response = client.chat.completions.create(
                        model=MODEL_ID,
                        messages=[
                            {"role": "system", "content": "You verify policy decisions from supplied facts; never invent facts."},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0,
                        max_tokens=100,
                        response_format={"type": "json_object"},
                    )
                except RateLimitError as exc:
                    retry_after = float((exc.response.headers or {}).get("retry-after", "5"))
                    time.sleep(min(max(retry_after, 1.0), 30.0))
                    response = client.chat.completions.create(
                        model=MODEL_ID,
                        messages=[
                            {"role": "system", "content": "You verify policy decisions from supplied facts; never invent facts."},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0,
                        max_tokens=100,
                        response_format={"type": "json_object"},
                    )
                self._last_request_at = time.monotonic()
                content = response.choices[0].message.content or "{}"
                parsed = json.loads(content)
                usage = response.usage
                return AuditResult(
                    attempted=True,
                    succeeded=True,
                    agreed=parsed.get("agreed") is True,
                    key_slot=slot,
                    prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                    completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                    response=parsed,
                )
            except AuthenticationError as exc:
                last_error = f"authentication error in key slot {slot}: {type(exc).__name__}"
                continue
            except Exception as exc:  # Audit failure must not corrupt deterministic output.
                return AuditResult(True, False, None, slot, 0, 0, {}, type(exc).__name__)
        return AuditResult(True, False, None, None, 0, 0, {}, last_error or "no usable API key")
