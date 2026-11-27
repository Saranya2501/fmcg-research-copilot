"""Command-line wrapper around the integrated P2/P3 runtime."""
import argparse
import json
import os
from pathlib import Path

from integration.runtime import run_query

P4_ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description="Competitive Research Copilot P4 integrated query runner")
    parser.add_argument("question", help="Research question")
    parser.add_argument(
        "--p2",
        default=os.getenv("P2_PACKAGE_PATH") or str(P4_ROOT / "integration/p2_agents"),
        help="Path to P2 agents (defaults to the bundled package)",
    )
    parser.add_argument(
        "--p3",
        default=os.getenv("P3_RAG_PATH") or str(P4_ROOT / "core"),
        help="Path to P3 retrieval and its data (defaults to the bundled runtime)",
    )
    args = parser.parse_args()
    result = run_query(args.question, args.p2, args.p3)
    print(json.dumps(result, indent=2, default=str))

if __name__ == "__main__":
    main()
