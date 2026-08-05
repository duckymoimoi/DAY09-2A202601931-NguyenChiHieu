from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from .build_reference_outputs import ROOT, build_reference_outputs


def _candidate(case_id: str, directory: Path, revision: str | None) -> dict[str, Any]:
    relative_path = f"output/{case_id}.json"
    if revision:
        content = subprocess.check_output(
            ["git", "show", f"{revision}:{relative_path}"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
        )
        return json.loads(content)
    return json.loads((directory / f"{case_id}.json").read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare candidate evidence with the reference oracle")
    parser.add_argument("--candidate", type=Path, default=ROOT / "output")
    parser.add_argument("--git-revision", help="Read output JSON from a Git revision instead")
    args = parser.parse_args()

    reference = build_reference_outputs()
    false_positives: Counter[str] = Counter()
    false_negatives: Counter[str] = Counter()
    issue_totals: Counter[str] = Counter()
    issue_matches: Counter[str] = Counter()
    case_rows: list[dict[str, Any]] = []
    total_expected = total_actual = total_matches = 0

    for case_id, expected_output in sorted(reference.items()):
        actual_output = _candidate(case_id, args.candidate, args.git_revision)
        issue = expected_output["assessment"]["primary_issue"]
        expected = set(expected_output["evidence_ids"])
        actual = set(actual_output["evidence_ids"])
        matches = expected & actual
        extra = actual - expected
        missing = expected - actual

        total_expected += len(expected)
        total_actual += len(actual)
        total_matches += len(matches)
        issue_totals[issue] += len(expected) + len(actual)
        issue_matches[issue] += 2 * len(matches)
        false_positives.update(f"{issue}/{value.split(':', 1)[0]}" for value in extra)
        false_negatives.update(f"{issue}/{value.split(':', 1)[0]}" for value in missing)

        denominator = len(expected) + len(actual)
        f1 = 2 * len(matches) / denominator if denominator else 1.0
        if extra or missing:
            case_rows.append(
                {
                    "case_id": case_id,
                    "issue": issue,
                    "f1": round(f1 * 100, 4),
                    "extra": sorted(extra),
                    "missing": sorted(missing),
                }
            )

    micro_denominator = total_expected + total_actual
    report = {
        "source": args.git_revision or str(args.candidate.resolve()),
        "expected_evidence": total_expected,
        "actual_evidence": total_actual,
        "matched_evidence": total_matches,
        "micro_f1": round(200 * total_matches / micro_denominator, 4),
        "f1_by_issue": {
            issue: round(100 * issue_matches[issue] / issue_totals[issue], 4)
            for issue in sorted(issue_totals)
        },
        "false_positives_by_issue_and_type": dict(sorted(false_positives.items())),
        "false_negatives_by_issue_and_type": dict(sorted(false_negatives.items())),
        "affected_cases": len(case_rows),
        "case_details": case_rows,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
