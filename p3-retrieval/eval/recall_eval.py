"""
M6: Recall@k evaluation for the RAG retrieval pipeline.

Usage:
    # With Yogesh's gold set:
    python eval/recall_eval.py --gold eval/gold_v1.jsonl

    # Also output a copy with 'context' field filled (for P2 Himanshu):
    python eval/recall_eval.py --gold eval/gold_v1.jsonl --fill-context

    # Quick 5-question smoke test (no gold file needed):
    python eval/recall_eval.py --smoke

Gold file format per GOLD_SCHEMA.pdf:
    {
      "id": "q017", "use_case": "UC2",
      "question": "Marico's A&P spend as % of revenue in FY24?",
      "answer_type": "number",
      "gold_source": {"doc": "Marico_AR_FY24.pdf", "page": 212},
      "context": ""   <- P3 fills this
    }
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

RAG_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAG_DIR))

from retrieve import retrieve, _load_models, _load_index, _chunk_map

K_VALUES = [5, 10]

# Maps PDF filename patterns to our doc_id convention.
# gold_source.doc = "Marico_AR_FY24.pdf" or "Marico_Annual_Report_FY24.pdf" etc.
# Our doc_id      = "marico_annual_report_fy24"
COMPANY_NAME_MAP = {
    # Exact folder names → canonical prefix used in our doc_ids
    "hul": "hul", "hindustan unilever": "hul",
    "itc": "itc",
    "nestle": "nestle", "nestlé": "nestle", "nestle india": "nestle",
    "dabur": "dabur",
    "britannia": "britannia",
    "marico": "marico",
    "godrej": "godrej_consumer", "gcpl": "godrej_consumer", "godrej consumer": "godrej_consumer",
    "colgate": "colgate",
    "tata consumer": "tata_consumer", "tcpl": "tata_consumer", "tata": "tata_consumer",
    "emami": "emami",
}


def pdf_filename_to_doc_id(doc_filename: str) -> str:
    """
    Convert gold_source.doc filename to our internal doc_id.
    E.g. "Marico_AR_FY24.pdf" → "marico_annual_report_fy24"
         "HUL_Annual_Report_2024.pdf" → "hul_annual_report_fy24"
    """
    stem = Path(doc_filename).stem.lower()

    # Extract fiscal year — try FYyy pattern first, then 4-digit year
    fy_match = re.search(r'fy(\d{2})', stem)
    year_match = re.search(r'(\d{4})', stem)
    if fy_match:
        fy = f"fy{fy_match.group(1)}"
    elif year_match:
        year = int(year_match.group(1))
        fy = f"fy{str(year)[-2:]}"
    else:
        fy = "fyunknown"

    # Extract company prefix
    company_prefix = None
    for key, val in COMPANY_NAME_MAP.items():
        if key in stem:
            company_prefix = val
            break

    if company_prefix is None:
        # Fallback: use first token before underscore/space
        company_prefix = re.split(r'[_\s]', stem)[0]

    return f"{company_prefix}_annual_report_{fy}"


def get_context_from_parsed(doc_id: str, page: int) -> str:
    """Look up the page text from our chunk map for the gold_source page."""
    if _chunk_map is None:
        return ""
    # Gather all chunks from that doc on that page
    page_chunks = [
        c for c in _chunk_map.values()
        if c.get("doc_id") == doc_id and c.get("page") == page
    ]
    if not page_chunks:
        # Try ±1 page
        page_chunks = [
            c for c in _chunk_map.values()
            if c.get("doc_id") == doc_id and abs(c.get("page", 0) - page) <= 1
        ]
    return "\n".join(c["text"] for c in sorted(page_chunks, key=lambda c: c.get("page", 0)))


SMOKE_QUESTIONS = [
    {
        "id": "smoke01", "question": "What were HUL's advertising and promotion expenses in FY24?",
        "gold_source": {"doc": "HUL_Annual_Report_2024.pdf", "page": None},
        "filters": {"company": "HUL", "fiscal_year": "FY24"},
    },
    {
        "id": "smoke02", "question": "What is Dabur's revenue from operations for FY2023?",
        "gold_source": {"doc": "Dabur_Annual_Report_2023.pdf", "page": None},
        "filters": {"company": "Dabur", "fiscal_year": "FY23"},
    },
    {
        "id": "smoke03", "question": "What is Nestle India's net profit for FY2024?",
        "gold_source": {"doc": "Nestle_Annual_Report_2024.pdf", "page": None},
        "filters": {"company": "Nestle India", "fiscal_year": "FY24"},
    },
    {
        "id": "smoke04", "question": "What is ITC's FMCG segment revenue in FY2023?",
        "gold_source": {"doc": "ITC_Annual_Report_2023.pdf", "page": None},
        "filters": {"company": "ITC", "fiscal_year": "FY23"},
    },
    {
        "id": "smoke05", "question": "Marico's volume growth in India business FY2024",
        "gold_source": {"doc": "Marico_Annual_Report_2024.pdf", "page": None},
        "filters": {"company": "Marico", "fiscal_year": "FY24"},
    },
]


def infer_filters(q: dict) -> dict | None:
    """Infer retrieval filters from gold_source when not explicitly provided."""
    filters = q.get("filters")
    if filters:
        return filters
    gold = q.get("gold_source", {})
    doc = gold.get("doc", "")
    if not doc:
        return None
    doc_id = pdf_filename_to_doc_id(doc)
    # Extract company from doc_id prefix and FY from suffix
    parts = doc_id.split("_annual_report_")
    if len(parts) == 2:
        company_key = parts[0]
        fy = parts[1].upper()  # e.g. "FY24"
        # Reverse lookup company alias
        FOLDER_TO_COMPANY = {
            "hul": "HUL", "itc": "ITC", "nestle": "Nestle India",
            "dabur": "Dabur", "britannia": "Britannia", "marico": "Marico",
            "godrej_consumer": "GCPL", "colgate": "Colgate-Palmolive India",
            "tata_consumer": "Tata Consumer Products", "emami": "Emami",
        }
        company = FOLDER_TO_COMPANY.get(company_key)
        if company and fy:
            return {"company": company, "fiscal_year": fy}
    return None


def evaluate(questions: list[dict], k_max: int = max(K_VALUES), fill_context: bool = False) -> tuple[dict, list[dict]]:
    hits = {k: 0 for k in K_VALUES}
    total = len(questions)
    latencies = []
    enriched = []

    print(f"\nEvaluating {total} questions…\n")
    for i, q in enumerate(questions):
        question = q["question"]
        gold = q.get("gold_source", {})
        gold_doc_file = gold.get("doc", "")
        gold_doc_id = pdf_filename_to_doc_id(gold_doc_file) if gold_doc_file else None
        gold_page = gold.get("page")
        filters = infer_filters(q)

        t0 = time.time()
        results = retrieve(question, k=k_max, filters=filters)
        latencies.append(time.time() - t0)

        retrieved_doc_ids = [r.get("doc_id") for r in results]

        def _doc_matches(retrieved_id: str, gold_id: str) -> bool:
            # doc_ids now include filename suffix: "hul_annual_report_fy24_hul_annual_report_2024"
            # gold_id is the shorter prefix: "hul_annual_report_fy24"
            return retrieved_id == gold_id or retrieved_id.startswith(gold_id + "_")

        for k in K_VALUES:
            top_k = results[:k]
            if gold_doc_id and any(_doc_matches(r.get("doc_id", ""), gold_doc_id) for r in top_k):
                hits[k] += 1
            elif gold_doc_id and gold_page:
                for r in top_k:
                    if _doc_matches(r.get("doc_id", ""), gold_doc_id) and r.get("page") is not None:
                        if abs(r.get("page") - gold_page) <= 1:
                            hits[k] += 1
                            break

        hit_at_5 = any(_doc_matches(d, gold_doc_id) for d in retrieved_doc_ids[:K_VALUES[0]]) if gold_doc_id else False
        status = "HIT" if hit_at_5 else "miss"
        print(f"[{i+1:3d}/{total}] {status}  {question[:70]}")
        if results:
            print(f"       top-1: {results[0].get('doc_id')}  p{results[0].get('page')}  score={results[0].get('score', 0):.3f}")
        print()

        if fill_context and gold_doc_id and gold_page:
            enriched_q = dict(q)
            enriched_q["context"] = get_context_from_parsed(gold_doc_id, gold_page)
            enriched.append(enriched_q)
        else:
            enriched.append(dict(q))

    recalls = {k: hits[k] / total for k in K_VALUES}
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    return {"recalls": recalls, "hits": hits, "total": total, "avg_latency_s": avg_latency}, enriched


def print_summary(results: dict):
    print("=" * 60)
    print("RECALL EVALUATION SUMMARY")
    print("=" * 60)
    for k, recall in results["recalls"].items():
        target = 0.70 if k == 5 else 0.80
        status = "PASS" if recall >= target else "FAIL"
        bar = "#" * int(recall * 20)
        print(f"  Recall@{k:<3}: {recall:.3f}  [{bar:<20}]  target={target:.2f}  {status}")
    print(f"  Questions: {results['total']}")
    print(f"  Avg latency: {results['avg_latency_s']:.2f}s / query")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", type=Path, help="Path to gold_v1.jsonl from P1 (Yogesh)")
    parser.add_argument("--smoke", action="store_true", help="Run 5-question smoke test")
    parser.add_argument("--fill-context", action="store_true",
                        help="Output gold file with 'context' field filled from parsed corpus")
    args = parser.parse_args()

    if not args.smoke and not args.gold:
        print("Pass --gold <path> or --smoke")
        sys.exit(1)

    print("Loading retrieval index…")
    _load_models()
    _load_index()
    print("Index loaded.\n")

    if args.smoke:
        questions = SMOKE_QUESTIONS
    else:
        questions = []
        with open(args.gold) as f:
            for line in f:
                line = line.strip()
                if line:
                    questions.append(json.loads(line))

    results, enriched = evaluate(questions, fill_context=args.fill_context)
    print_summary(results)

    if args.fill_context and args.gold:
        out_path = args.gold.parent / (args.gold.stem + "_with_context.jsonl")
        with open(out_path, "w") as f:
            for q in enriched:
                f.write(json.dumps(q, ensure_ascii=False) + "\n")
        print(f"\nContext-filled gold set written to: {out_path}")


if __name__ == "__main__":
    main()
