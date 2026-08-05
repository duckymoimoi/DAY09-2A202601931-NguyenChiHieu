from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values


# The assignment requires this value to be visible in source code and <= 10B.
MODEL_ID = "llama-3.1-8b-instant"
MODEL_PARAMETER_SIZE_B = 8
POLICY_VERSION = "EC_POLICY_V1"
PAYMENT_TOLERANCE_BRL = "0.10"


@dataclass(frozen=True)
class Settings:
    root: Path
    input_dir: Path
    data_dir: Path
    output_dir: Path
    logging_dir: Path
    api_keys: tuple[str, ...]
    base_url: str
    llm_audit: bool = False


def _candidate_env_files(root: Path) -> list[Path]:
    return [root / ".env", root.parent / ".env"]


def _load_secret_values(root: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for path in _candidate_env_files(root):
        if path.exists():
            for key, value in dotenv_values(path).items():
                if value and key not in values:
                    values[key] = value
    for key, value in os.environ.items():
        if value:
            values[key] = value
    return values


def load_settings(root: Path | None = None, *, llm_audit: bool = False) -> Settings:
    project_root = (root or Path(__file__).resolve().parents[1]).resolve()
    values = _load_secret_values(project_root)
    ordered_names = ["OPENAI_API_KEY"] + [f"OPENAI_API_KEY_{index}" for index in range(2, 8)]
    keys = tuple(dict.fromkeys(values[name] for name in ordered_names if values.get(name)))
    return Settings(
        root=project_root,
        input_dir=project_root / "input",
        data_dir=project_root / "data",
        output_dir=project_root / "output",
        logging_dir=project_root / "logging",
        api_keys=keys,
        base_url=values.get("OPENAI_BASE_URL", "https://api.groq.com/openai/v1"),
        llm_audit=llm_audit,
    )

