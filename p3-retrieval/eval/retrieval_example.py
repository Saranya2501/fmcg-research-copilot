"""
P3 Retrieval — Working example for P4 (Rohit).

Demonstrates retrieve() and get_table() on 3 real gold-set questions
(one UC1, one UC2, one UC3) and prints the full output schema.

Run from p3-retrieval/:
    python3 eval/retrieval_example.py

Requires index/ and parsed/ symlinks or directories to be in place.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from retrieve import retrieve, get_table, _load_models, _load_index

# ── Queries drawn from gold_v1.jsonl ──────────────────────────────────────────

EXAMPLES = [
    {
        "id": "q001",
        "use_case": "UC1 — single-company metric",
        "question": "What was Hindustan Unilever's revenue from operations in FY24?",
        "filters": {"company": "HUL", "fiscal_year": "FY24"},
        "expected": "61,896 Rs crore (consolidated, FY ended 31 March 2024)",
    },
    {
        "id": "q021",
        "use_case": "UC2 — calculation",
        "question": "Calculate Marico's A&P spend as a percentage of revenue from operations for FY24.",
        "filters": {"company": "Marico", "fiscal_year": "FY24"},
        "expected": "9.86% (952 ÷ 9,653 × 100; consolidated)",
    },
    {
        "id": "q039",
        "use_case": "UC3 — ranking across companies",
        "question": "Rank HUL, Dabur, Marico and Emami by FY24 revenue-from-operations growth.",
        "filters": {"fiscal_year": "FY24", "doc_type": "annual_report"},
        "expected": "Dabur (7.58%) > Emami (5.06%) > HUL (2.17%) > Marico (−1.14%)",
    },
]

DIVIDER = "─" * 72


def run_example(ex: dict, k: int = 5):
    print(f"\n{DIVIDER}")
    print(f"[{ex['id']}] {ex['use_case']}")
    print(f"Q: {ex['question']}")
    print(f"Expected answer: {ex['expected']}")
    print(f"Filters: {ex['filters']}")
    print()

    t0 = time.time()
    chunks = retrieve(ex["question"], k=k, filters=ex["filters"])
    elapsed = time.time() - t0

    print(f"retrieve(k={k}) → {len(chunks)} results  [{elapsed:.2f}s]")
    print()

    for i, c in enumerate(chunks, 1):
        print(f"  [{i}] score={c['score']:.3f}")
        print(f"       chunk_id:   {c['chunk_id']}")
        print(f"       doc_id:     {c['doc_id']}")
        print(f"       company:    {c['company']}  |  {c['fiscal_year']}  |  {c['doc_type']}")
        print(f"       section:    {c['section']}  |  page {c['page']}  |  basis: {c.get('standalone_consolidated','?')}")
        # Strip <<DATA>>…<<END DATA>> for readability
        text = c["text"]
        if "<<DATA>>" in text:
            text = text.split("<<DATA>>", 1)[1]
            if "<<END DATA>>" in text:
                text = text.rsplit("<<END DATA>>", 1)[0]
            lines = text.strip().splitlines()
            if lines and lines[0].startswith("[Source:"):
                text = "\n".join(lines[1:]).strip()
        snippet = text[:350].replace("\n", " ")
        print(f"       text[0:350]: {snippet}…")
        print()

    if not chunks:
        return

    # Demonstrate get_table() on the top result
    top = chunks[0]
    print(f"  get_table(doc_id={top['doc_id']!r}, page={top['page']}, section_hint={top['section']!r})")
    table = get_table(top["doc_id"], page=top["page"], section_hint=top["section"])

    print(f"  → low_confidence: {table['low_confidence']}")
    print(f"    page={table.get('page')}  section={table.get('section')}")

    if table["low_confidence"]:
        fb = table.get("text_fallback", "")
        print(f"    text_fallback[0:200]: {fb[:200]}")
    else:
        headers = table.get("headers", [])
        rows    = table.get("rows", [])
        print(f"    headers: {headers}")
        for row in rows[:5]:
            print(f"    row:     {row}")
        if len(rows) > 5:
            print(f"    … (+{len(rows)-5} more rows)")

    # Full schema as JSON for Rohit's reference
    print(f"\n  Full retrieve() output schema (first result):")
    schema_ref = {k: v for k, v in chunks[0].items() if k != "text"}
    schema_ref["text"] = "<<DATA>> [Source: ...] …chunk text… <<END DATA>>"
    print("  " + json.dumps(schema_ref, indent=4).replace("\n", "\n  "))


def main():
    print("Loading models and index…")
    t0 = time.time()
    _load_models()
    _load_index()
    from retrieve import _chunk_map
    print(f"Ready: {len(_chunk_map):,} chunks  [{time.time()-t0:.1f}s]\n")

    for ex in EXAMPLES:
        run_example(ex)

    print(f"\n{DIVIDER}")
    print("All examples complete.")
    print()
    print("Citation format for P4 Writer agent:")
    print("  [Company, Document Title, p. N]")
    print("  e.g. [HUL, Annual Report FY24, p. 179]")
    print()
    print("Index coverage (see INTEGRATION.md for full details):")
    print("  406 PDFs → 113,405 chunks")
    print("  Annual reports: all 10 companies FY17–FY26 (Nestle FY23 missing)")
    print("  Quarterly: HUL, ITC, Tata Consumer, GCPL, Britannia, Nestle FY21–FY26")
    print("  Quarterly gaps: Dabur, Marico, Emami, Colgate (annual reports only)")


if __name__ == "__main__":
    main()
