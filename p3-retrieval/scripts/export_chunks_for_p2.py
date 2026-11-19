"""
Export a representative chunk sample for P2 (Himanshu) prompt testing.

Reads all_chunks.jsonl from the local RAG parsed directory and outputs
~50 chunks per company in Himanshu's required format:
  chunk_id, company, fiscal_year, quarter, doc_type, doc, page, section, text

Run from repo root:
    python3 p3-retrieval/scripts/export_chunks_for_p2.py
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

PARSED_DIR = Path(__file__).resolve().parents[2] / "RAG" / "parsed"
if not PARSED_DIR.exists():
    # Try the old working location
    PARSED_DIR = Path("/Users/ssekar/upgrad All Docs/Capstone Project/RAG/parsed")

ALL_CHUNKS = PARSED_DIR / "all_chunks.jsonl"
OUT_FILE = Path(__file__).resolve().parent.parent / "eval" / "chunks_sample_p2.jsonl"

CHUNKS_PER_COMPANY = 50   # ~500 total across 10 companies
SECTION_BUDGET = {        # rough spread per company: prefer financial sections
    "P&L": 10,
    "Balance Sheet": 8,
    "MD&A": 8,
    "Segment Results": 6,
    "Notes to Accounts": 6,
    "Cash Flow": 4,
    "General": 8,
}

FY_RE = re.compile(r"_fy\d{2,4}_", re.IGNORECASE)
Q_RE  = re.compile(r"_Q([1-4])_", re.IGNORECASE)


def doc_filename(doc_id: str) -> str:
    """Extract original filename stem from doc_id and append .pdf."""
    m = FY_RE.search(doc_id)
    if m:
        stem = doc_id[m.end():]   # everything after _fyNN_
        return stem + ".pdf"
    return doc_id + ".pdf"


def quarter(doc_id: str):
    m = Q_RE.search(doc_id)
    return f"Q{m.group(1)}" if m else None


def to_himanshu(chunk: dict) -> dict:
    return {
        "chunk_id":    chunk["chunk_id"],
        "company":     chunk["company"],
        "fiscal_year": chunk["fiscal_year"],
        "quarter":     quarter(chunk["doc_id"]),
        "doc_type":    chunk["doc_type"],
        "doc":         doc_filename(chunk["doc_id"]),
        "page":        chunk["page"],
        "section":     chunk.get("section", "General"),
        "text":        chunk["text"],   # raw text, no <<DATA>> wrapping
    }


def main():
    if not ALL_CHUNKS.exists():
        print(f"ERROR: {ALL_CHUNKS} not found", file=sys.stderr)
        sys.exit(1)

    # Bucket chunks by (company, section) → keep up to SECTION_BUDGET[section] per company
    buckets: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    section_keys = set(SECTION_BUDGET)

    with open(ALL_CHUNKS) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            chunk = json.loads(line)
            company = chunk.get("company", "")
            section = chunk.get("section", "General")
            bucket_section = section if section in section_keys else "General"
            company_buckets = buckets[company]
            if len(company_buckets[bucket_section]) < SECTION_BUDGET.get(bucket_section, 4):
                company_buckets[bucket_section].append(chunk)

    # Flatten and cap at CHUNKS_PER_COMPANY per company
    output = []
    for company, sec_map in sorted(buckets.items()):
        company_chunks = []
        for section_chunks in sec_map.values():
            company_chunks.extend(section_chunks)
        output.extend(company_chunks[:CHUNKS_PER_COMPANY])

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    mapped = [to_himanshu(c) for c in output]
    with open(OUT_FILE, "w") as f:
        for row in mapped:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Wrote {len(mapped)} chunks to {OUT_FILE}")

    # Quick sanity check
    companies = {c["company"] for c in mapped}
    sections  = {c["section"] for c in mapped}
    quarters  = {c["quarter"] for c in mapped if c["quarter"]}
    print(f"  Companies ({len(companies)}): {sorted(companies)}")
    print(f"  Sections  ({len(sections)}): {sorted(sections)}")
    print(f"  Quarters with data: {sorted(quarters)}")
    print(f"  Doc types: {sorted({c['doc_type'] for c in mapped})}")


if __name__ == "__main__":
    main()
