from __future__ import annotations

import json
import zipfile
from pathlib import Path

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

    zip_path = settings.root / "output.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in actual_paths:
            archive.write(path, arcname=path.name)

    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        if names != [path.name for path in actual_paths]:
            raise ValueError("Archive content/order mismatch")
        for name in names:
            json.loads(archive.read(name))

    print(
        json.dumps(
            {
                "validated_outputs": len(actual_paths),
                "issue_counts": dict(sorted(issue_counts.items())),
                "archive": str(zip_path),
                "archive_files": len(actual_paths),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

