from __future__ import annotations

import json

from app.agents import VerifierAgent
from app.config import load_settings
from app.contracts import CaseOutput
from app.data_repository import DataRepository
from app.pipeline import load_cases


def main() -> None:
    settings = load_settings()
    loaded = load_cases(settings.input_dir)
    expected_names = {path.name for path, _ in loaded}
    actual_paths = sorted(settings.output_dir.glob("*.json"))
    actual_names = {path.name for path in actual_paths}
    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        extra = sorted(actual_names - expected_names)
        raise ValueError(f"Output filename mismatch; missing={missing}, extra={extra}")

    unexpected_files = sorted(
        path.name
        for path in settings.output_dir.iterdir()
        if path.is_file() and path.suffix.lower() != ".json"
    )
    if unexpected_files:
        raise ValueError(f"Unexpected non-JSON files in output/: {unexpected_files}")

    repository = DataRepository.load(
        settings.data_dir,
        {case.customer_request.claimed_order_id for _, case in loaded},
    )
    cases_by_name = {path.name: case for path, case in loaded}
    verifier = VerifierAgent()
    issue_counts: dict[str, int] = {}
    for path in actual_paths:
        output = CaseOutput.model_validate_json(path.read_text(encoding="utf-8"))
        case = cases_by_name[path.name]
        errors = verifier.verify(repository.context_for(case), output)
        if errors:
            raise ValueError(f"{path.name} failed verification: {errors}")
        issue = output.assessment.primary_issue
        issue_counts[issue] = issue_counts.get(issue, 0) + 1

    print(
        json.dumps(
            {
                "validated_outputs": len(actual_paths),
                "issue_counts": dict(sorted(issue_counts.items())),
                "output_directory": str(settings.output_dir),
                "non_json_files": unexpected_files,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

