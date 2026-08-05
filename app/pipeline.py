from __future__ import annotations

import json
import platform
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from .agents import DeliveryAgent, OrderSellerAgent, PaymentAgent, PolicyAgent, VerifierAgent
from .config import MODEL_ID, MODEL_PARAMETER_SIZE_B, Settings
from .contracts import InputCase, InvestigationBundle
from .data_repository import DataRepository
from .llm_audit import GroqPolicyAuditAgent
from .trace import TraceWriter


def load_cases(input_dir: Path) -> list[tuple[Path, InputCase]]:
    files = sorted(input_dir.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"No JSON inputs found in {input_dir}")
    cases: list[tuple[Path, InputCase]] = []
    seen_cases: set[str] = set()
    seen_orders: set[str] = set()
    for path in files:
        try:
            case = InputCase.model_validate_json(path.read_text(encoding="utf-8"))
        except ValidationError as exc:
            raise ValueError(f"Invalid input {path.name}: {exc}") from exc
        if path.stem != case.case_id:
            raise ValueError(f"Filename {path.name} does not match case_id {case.case_id}")
        if case.case_id in seen_cases:
            raise ValueError(f"Duplicate case_id: {case.case_id}")
        order_id = case.customer_request.claimed_order_id
        if order_id in seen_orders:
            raise ValueError(f"Duplicate claimed_order_id: {order_id}")
        seen_cases.add(case.case_id)
        seen_orders.add(order_id)
        cases.append((path, case))
    return cases


class MultiAgentPipeline:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.run_id = uuid.uuid4().hex
        self.trace = TraceWriter(settings.logging_dir / "trace.jsonl", self.run_id)
        self.order_agent = OrderSellerAgent()
        self.payment_agent = PaymentAgent()
        self.delivery_agent = DeliveryAgent()
        self.policy_agent = PolicyAgent()
        self.verifier_agent = VerifierAgent()
        self.audit_agent = GroqPolicyAuditAgent(settings)

    def run(self) -> dict[str, object]:
        started = datetime.now(timezone.utc)
        loaded = load_cases(self.settings.input_dir)
        targets = {case.customer_request.claimed_order_id for _, case in loaded}
        repository = DataRepository.load(self.settings.data_dir, targets)

        self.settings.output_dir.mkdir(parents=True, exist_ok=True)
        for old_output in self.settings.output_dir.glob("*.json"):
            old_output.unlink()

        issue_counts: Counter[str] = Counter()
        audit_attempts = 0
        audit_successes = 0
        audit_agreements = 0
        prompt_tokens = 0
        completion_tokens = 0

        for input_path, case in loaded:
            context = repository.context_for(case)
            self.trace.emit(case.case_id, "case_received", "coordinator_agent", payload={"source": input_path.name})

            self.trace.emit(case.case_id, "handoff", "coordinator_agent", target=self.order_agent.name)
            order_facts = self.order_agent.investigate(context)
            self.trace.emit(case.case_id, "agent_result", self.order_agent.name, target="coordinator_agent", payload=order_facts.model_dump(mode="json"))

            self.trace.emit(case.case_id, "handoff", "coordinator_agent", target=self.payment_agent.name)
            payment_facts = self.payment_agent.investigate(context)
            self.trace.emit(case.case_id, "agent_result", self.payment_agent.name, target="coordinator_agent", payload=payment_facts.model_dump(mode="json"))

            self.trace.emit(case.case_id, "handoff", "coordinator_agent", target=self.delivery_agent.name)
            delivery_facts = self.delivery_agent.investigate(context)
            self.trace.emit(case.case_id, "agent_result", self.delivery_agent.name, target="coordinator_agent", payload=delivery_facts.model_dump(mode="json"))

            bundle = InvestigationBundle(
                case_id=case.case_id,
                order=order_facts,
                payment=payment_facts,
                delivery=delivery_facts,
            )
            self.trace.emit(case.case_id, "handoff", "coordinator_agent", target=self.policy_agent.name, payload={"contract": "InvestigationBundle"})
            decision, output = self.policy_agent.decide(context, bundle)
            issue_counts[decision.primary_issue] += 1
            self.trace.emit(
                case.case_id,
                "agent_result",
                self.policy_agent.name,
                target=self.verifier_agent.name,
                payload={"primary_issue": decision.primary_issue, "cause_code": decision.cause_code, "refund_brl": f"{decision.refund:.2f}"},
            )

            audit = self.audit_agent.audit(bundle, decision.primary_issue)
            audit_attempts += int(audit.attempted)
            audit_successes += int(audit.succeeded)
            audit_agreements += int(audit.agreed is True)
            prompt_tokens += audit.prompt_tokens
            completion_tokens += audit.completion_tokens
            self.trace.emit(
                case.case_id,
                "model_audit",
                self.audit_agent.name,
                target=self.verifier_agent.name,
                payload={
                    "model": MODEL_ID,
                    "attempted": audit.attempted,
                    "succeeded": audit.succeeded,
                    "agreed": audit.agreed,
                    "key_slot": audit.key_slot,
                    "prompt_tokens": audit.prompt_tokens,
                    "completion_tokens": audit.completion_tokens,
                    "response": audit.response,
                    "error": audit.error,
                },
            )

            errors = self.verifier_agent.verify(context, output)
            self.trace.emit(case.case_id, "verification", self.verifier_agent.name, target="coordinator_agent", payload={"passed": not errors, "errors": errors})
            if errors:
                raise ValueError(f"Verifier rejected {case.case_id}: {errors}")

            destination = self.settings.output_dir / input_path.name
            temporary = destination.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(output.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(destination)
            self.trace.emit(case.case_id, "output_written", "coordinator_agent", payload={"destination": destination.name})

        finished = datetime.now(timezone.utc)
        metadata: dict[str, object] = {
            "run_id": self.run_id,
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "cases_processed": len(loaded),
            "issue_counts": dict(sorted(issue_counts.items())),
            "model": {
                "provider": "Groq",
                "name": MODEL_ID,
                "parameter_size_billion": MODEL_PARAMETER_SIZE_B,
                "role": "non_authoritative_policy_audit",
            },
            "llm_audit": {
                "enabled": self.settings.llm_audit,
                "attempts": audit_attempts,
                "successes": audit_successes,
                "agreements": audit_agreements,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            },
            "framework": "custom_typed_multi_agent_orchestrator",
            "runtime": {
                "language": "Python",
                "python_version": platform.python_version(),
                "platform": sys.platform,
            },
            "agents": [
                "coordinator_agent",
                self.order_agent.name,
                self.payment_agent.name,
                self.delivery_agent.name,
                self.policy_agent.name,
                self.audit_agent.name,
                self.verifier_agent.name,
            ],
        }
        metadata_path = self.settings.logging_dir / "metadata.json"
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return metadata

