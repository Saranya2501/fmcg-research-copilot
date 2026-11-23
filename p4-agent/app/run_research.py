"""Command-line wrapper around the integrated P2/P3 runtime."""
import argparse, json, os
from integration.runtime import run_query


def main():
    parser = argparse.ArgumentParser(description="Competitive Research Copilot P4 integrated query runner")
    parser.add_argument("question", help="Research question")
    parser.add_argument("--p2", default=os.getenv("P2_PACKAGE_PATH"), help="Path to extracted P2 agents package")
    parser.add_argument("--p3", default=os.getenv("P3_RAG_PATH"), help="Path to P3 RAG runtime (retrieve.py, index/, parsed/)")
    args = parser.parse_args()
    if not args.p2 or not args.p3:
        parser.error("Set P2_PACKAGE_PATH and P3_RAG_PATH or pass --p2 and --p3")
    result = run_query(args.question, args.p2, args.p3)
    print(json.dumps(result, indent=2, default=str))

if __name__ == "__main__":
    main()
