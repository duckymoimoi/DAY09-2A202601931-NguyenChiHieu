from __future__ import annotations

from collections import Counter
from dataclasses import replace

from app.agents import VerifierAgent
from app.config import load_settings
from app.contracts import CaseOutput
from app.data_repository import DataRepository
from app.pipeline import MultiAgentPipeline, load_cases
from app.policy import POLICY_RULES, evaluate_policy
from scripts.build_reference_outputs import build_reference_outputs


def _load_contexts():
    settings = load_settings()
    loaded = load_cases(settings.input_dir)
    repository = DataRepository.load(
        settings.data_dir,
        {case.customer_request.claimed_order_id for _, case in loaded},
    )
    return settings, loaded, repository, [repository.context_for(case) for _, case in loaded]


def test_all_inputs_are_generic_and_resolvable() -> None:
    _, loaded, _, contexts = _load_contexts()
    assert len(loaded) == 50
    assert len({case.case_id for _, case in loaded}) == 50
    counts = Counter(evaluate_policy(context).primary_issue for context in contexts)
    assert counts == {
        "canceled_order_paid": 8,
        "unavailable_order_paid": 8,
        "late_delivery_seller": 8,
        "late_delivery_logistics": 8,
        "valid_split_payment": 9,
        "unsupported_late_claim": 9,
    }


def test_policy_priority_resolves_overlapping_rules() -> None:
    _, _, _, contexts = _load_contexts()
    rules = POLICY_RULES["EC_POLICY_V1"]
    overlaps = [context for context in contexts if sum(rule.matches(context) for rule in rules) > 1]
    assert len(overlaps) == 9
    assert all(evaluate_policy(context).primary_issue == "valid_split_payment" for context in overlaps)


def test_unavailable_orders_without_items_are_valid() -> None:
    _, _, _, contexts = _load_contexts()
    contexts = [context for context in contexts if context.order.status == "unavailable"]
    assert len(contexts) == 8
    for context in contexts:
        assert context.items == ()
        assert context.item_total == 0
        assert context.freight_total == 0
        decision = evaluate_policy(context)
        assert decision.primary_issue == "unavailable_order_paid"
        assert decision.refund == context.payment_total


def test_generated_outputs_pass_independent_verifier(tmp_path) -> None:
    settings, loaded, repository, _ = _load_contexts()
    reference_outputs = build_reference_outputs(settings.root)
    isolated = replace(
        settings,
        output_dir=tmp_path / "output",
        logging_dir=tmp_path / "logging",
        llm_audit=False,
    )
    metadata = MultiAgentPipeline(isolated).run()
    assert metadata["cases_processed"] == 50
    verifier = VerifierAgent()
    for input_path, case in loaded:
        output_path = isolated.output_dir / input_path.name
        output = CaseOutput.model_validate_json(output_path.read_text(encoding="utf-8"))
        assert verifier.verify(repository.context_for(case), output) == []
        assert output.assessment.confidence == 1.0
        assert output.model_dump(mode="json") == reference_outputs[case.case_id]


def test_outputs_only_include_rule_relevant_evidence(tmp_path) -> None:
    settings, loaded, repository, _ = _load_contexts()
    isolated = replace(
        settings,
        output_dir=tmp_path / "output",
        logging_dir=tmp_path / "logging",
        llm_audit=False,
    )
    MultiAgentPipeline(isolated).run()
    evidence_types = {
        "ORDER_CANCELED_AFTER_PAYMENT": {"order", "payment", "policy"},
        "ORDER_UNAVAILABLE_AFTER_PAYMENT": {"order", "payment", "policy"},
        "SELLER_HANDOFF_AFTER_LIMIT": {"order", "item", "payment", "seller", "policy"},
        "CARRIER_DELIVERED_AFTER_ESTIMATE": {"order", "item", "payment", "policy"},
        "MULTIPLE_PAYMENTS_RECONCILED": {"order", "item", "payment", "policy"},
        "DELIVERY_WITHIN_ESTIMATE": {"order", "item", "payment", "policy"},
    }
    for input_path, case in loaded:
        context = repository.context_for(case)
        cause = evaluate_policy(context).cause_code
        output = CaseOutput.model_validate_json(
            (isolated.output_dir / input_path.name).read_text(encoding="utf-8")
        )
        actual_types = {evidence.split(":", 1)[0] for evidence in output.evidence_ids}
        assert actual_types == evidence_types[cause]


def test_stored_reference_set_matches_independent_oracle() -> None:
    settings = load_settings()
    expected = build_reference_outputs(settings.root)
    reference_paths = sorted((settings.root / "reference_output").glob("EC_*.json"))
    assert len(reference_paths) == 50
    for path in reference_paths:
        actual = CaseOutput.model_validate_json(path.read_text(encoding="utf-8"))
        assert actual.model_dump(mode="json") == expected[actual.case_id]
