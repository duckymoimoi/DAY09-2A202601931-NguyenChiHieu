from __future__ import annotations

import argparse
import json

from .config import load_settings
from .pipeline import MultiAgentPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resolve Olist disputes with a typed multi-agent pipeline")
    parser.add_argument(
        "--llm-audit",
        action="store_true",
        help="Call Groq 8B as a non-authoritative audit agent for each case",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = load_settings(llm_audit=args.llm_audit)
    metadata = MultiAgentPipeline(settings).run()
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

