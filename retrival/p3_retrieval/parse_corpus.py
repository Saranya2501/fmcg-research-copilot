"""
M3: Parse all PDFs in the Corpus into chunked JSON.
Handles annual reports, quarterly results, and investor presentations.
Outputs one JSONL file per document in parsed/, plus a combined all_chunks.jsonl.

To add new files:
  1. Place PDFs in the correct Corpus subfolder (Annual reports / Quarterly results / Investor presentations)
  2. Delete parsed/<doc_id>.jsonl and all index files (index/*.pkl, index/*.index, index/*.json)
  3. Re-run parse_corpus.py then build_index.py
"""

import fitz  # PyMuPDF
import json
import os
import re
import sys
from pathlib import Path
from tqdm import tqdm

# ── Paths ────────────────────────────────────────────────────────────────────
RAG_DIR = Path(__file__).resolve().parent
# Scan all subfolders of Corpus (Annual reports, Quarterly results, etc.)
CORPUS_ROOT = RAG_DIR.parents[1] / "Corpus"
PARSED_DIR = RAG_DIR / "parsed"
PARSED_DIR.mkdir(exist_ok=True)

# ── Chunk settings ───────────────────────────────────────────────────────────
CHUNK_CHARS = 1800   # ~450 tokens at 4 chars/token (conservative, leaves room for metadata)
OVERLAP_CHARS = 200  # ~50 token overlap

# ── Company canonical names ───────────────────────────────────────────────────
# Maps folder name → canonical name used in queries and citations
COMPANY_ALIASES = {
    "Britannia": "Britannia",
    "Dabur": "Dabur",
    "HUL": "HUL",
    "Marico": "Marico",
    "Nestle": "Nestle India",
    "Emami": "Emami",
    "ITC": "ITC",
    "Tata Consumer": "Tata Consumer Products",
    "Colgate": "Colgate-Palmolive India",
    "Godrej Consumer": "GCPL",
}

# ── Section detection ─────────────────────────────────────────────────────────
# Order matters: more specific patterns first
SECTION_PATTERNS = [
    (r"statement of profit and loss|profit and loss account", "P&L"),
    (r"balance sheet", "Balance Sheet"),
    (r"cash flow statement", "Cash Flow"),
    (r"notes to (?:the )?(?:financial|standalone|consolidated)", "Notes to Accounts"),
    (r"segment(?:al)? (?:results|revenue|information|report)", "Segment Results"),
    (r"management(?:'s)? discussion and analysis|md&a", "MD&A"),
    (r"(?:independent )?auditor'?s? report", "Auditor's Report"),
    (r"(?:board'?s?|directors'?) report", "Directors' Report"),
    (r"corporate governance", "Corporate Governance"),
    (r"business responsibility", "BRSR"),
    (r"(?:five|10|ten)[- ]year(?:s)? (?:financial )?(?:highlights?|summary|data)", "Financial Highlights"),
    (r"chairman(?:'s)? (?:message|letter|statement)", "Chairman's Message"),
    (r"(?:managing director|md|ceo)(?:'s)? (?:message|letter|review)", "MD's Message"),
    (r"notice of (?:the )?(?:annual general meeting|agm)", "AGM Notice"),
]

SECTION_RE = [(re.compile(pat, re.IGNORECASE), label) for pat, label in SECTION_PATTERNS]


def detect_section(text: str) -> str:
    """Detect section from first 600 chars of a page."""
    snippet = text[:600]
    for pattern, label in SECTION_RE:
        if pattern.search(snippet):
            return label
    return "General"


def detect_consolidated(text: str) -> str:
    """Detect standalone vs consolidated from page text."""
    snippet = text[:2000].upper()
    if "CONSOLIDATED" in snippet:
        return "consolidated"
    if "STANDALONE" in snippet:
        return "standalone"
    return "unknown"


def parse_filename(pdf_path: Path) -> tuple[str, str, str, str]:
    """
    Extract (company, fiscal_year, doc_type, doc_id) from path.

    Annual report:    HUL/HUL_Annual_Report_2024.pdf
                      → company='HUL', fy='FY24', doc_type='annual_report'
    Quarterly result: HUL/Quarterly results/HUL_Q4_Results_FY24.pdf
                      → company='HUL', fy='FY24', doc_type='quarterly_results'
    Investor pres:    HUL/Investor presentations/HUL_Investor_Day_FY24.pdf
                      → company='HUL', fy='FY24', doc_type='investor_presentation'
    """
    name = pdf_path.stem
    # Company folder is the top-level subfolder under Corpus
    # Path may be: Corpus/Annual reports/HUL/file.pdf  → folder = HUL
    #           or: Corpus/HUL/Quarterly results/file.pdf → folder = HUL
    parts = pdf_path.relative_to(CORPUS_ROOT).parts
    folder = parts[1] if len(parts) > 2 else parts[0]

    # Detect doc_type from parent folder or filename keywords
    # Note: ITC folder is misspelled "Quaterly Results" — handle both spellings
    parent_lower = pdf_path.parent.name.lower()
    name_lower = name.lower()
    if "quarterly" in parent_lower or "quaterly" in parent_lower or re.search(r'q[1-4]', name_lower):
        doc_type = "quarterly_results"
    elif "investor" in parent_lower or "presentation" in parent_lower:
        doc_type = "investor_presentation"
    else:
        doc_type = "annual_report"

    # Quarter detection from filename
    q_match = re.search(r'q([1-4])', name_lower)
    quarter_num = int(q_match.group(1)) if q_match else None

    # FY year detection (priority order):
    # 0. FY + YYYY-YY range: "FY2024-25" → FY25 (must beat plain fy_match)
    fy_range_match = re.search(r'fy\s*(\d{4})[_-](\d{2})(?!\d)', name_lower)
    # 1. Explicit FYyy or FY20yy: "FY24", "FY2024"
    fy_match = re.search(r'fy\s*(\d{2,4})', name_lower)
    # 2. Indian FY "YYYY_YY" / "YYYY-YY" without fy prefix: "2022_23" → FY23
    #    Use (?!\d) instead of \b so underscores (which are \w) don't block matching.
    #    Validate: ending year must be (start_year % 100 + 1) and start_year >= 2000.
    indian_fy_match = re.search(r'(\d{4})[_-](\d{2})(?!\d)', name)
    # 3. Date DD_MM_YYYY or DD.MM.YYYY: "30_06_2021" → Q1 FY22
    date_match = re.search(r'\b(\d{2})[._-](\d{2})[._-](\d{4})\b', name)
    # 4. 4-digit year not surrounded by other digits: "2022" in "Report_2022.pdf".
    #    Use negative lookaround on digits (not \b) so "_2017" in filenames still matches
    #    but "9474" inside a hash like "99cd947489" (adjacent digits on both sides) does not.
    year_match = re.search(r'(?<![0-9])(\d{4})(?![0-9])', name)

    fy_short = "FYunknown"
    if fy_range_match:
        # "FY2024-25" → group(2) = "25" → FY25
        fy_short = f"FY{fy_range_match.group(2)}"
    elif fy_match:
        raw = fy_match.group(1)
        fy_short = f"FY{raw[-2:]}"
    elif indian_fy_match:
        year4 = int(indian_fy_match.group(1))
        ending = int(indian_fy_match.group(2))
        expected = (year4 % 100 + 1) % 100
        # Only accept if the year looks plausible and ending matches YYYY+1 convention
        if year4 >= 2000 and ending == expected:
            fy_short = f"FY{indian_fy_match.group(2)}"
    elif date_match:
        day, month, cal_year = int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3))
        # Indian FY starts April: Apr–Dec → FY = cal_year+1; Jan–Mar → FY = cal_year
        fy_year = cal_year + 1 if month >= 4 else cal_year
        fy_short = f"FY{str(fy_year)[-2:]}"
        if quarter_num is None:
            q_map = {4: 1, 5: 1, 6: 1, 7: 2, 8: 2, 9: 2, 10: 3, 11: 3, 12: 3, 1: 4, 2: 4, 3: 4}
            quarter_num = q_map.get(month)
    elif year_match:
        year = int(year_match.group(1))
        # Only accept plausible years (hash suffixes often contain 4-digit non-year sequences)
        if 2000 <= year <= 2035:
            fy_short = f"FY{str(year)[-2:]}"

    quarter_tag = f"_Q{quarter_num}" if quarter_num else ""

    company = COMPANY_ALIASES.get(folder, folder)
    safe_folder = folder.lower().replace(" ", "_")
    # Include sanitised filename stem to guarantee uniqueness across files sharing the same Q+FY
    # (e.g. results PDF vs presentation PDF vs transcript for the same quarter)
    safe_name = re.sub(r'[^a-z0-9]+', '_', name_lower).strip('_')[:60]
    doc_id = f"{safe_folder}_{doc_type}{quarter_tag}_{fy_short}_{safe_name}".lower()
    return company, fy_short, doc_type, doc_id


def chunk_text(text: str, chunk_size: int = CHUNK_CHARS, overlap: int = OVERLAP_CHARS) -> list[str]:
    """Split text into overlapping chunks."""
    if not text.strip():
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        # Try to break at a sentence boundary within last 200 chars
        if end < len(text):
            boundary = text.rfind('. ', max(start, end - 200), end)
            if boundary > start:
                end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        next_start = end - overlap
        if next_start <= start:  # guard against infinite loop on short text
            break
        start = next_start
    return chunks


def parse_pdf(pdf_path: Path) -> list[dict]:
    """Parse one PDF → list of chunk dicts (C1: fixed-size text chunks)."""
    company, fy, doc_type, doc_id = parse_filename(pdf_path)
    chunks = []
    chunk_idx = 0

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        print(f"  ERROR opening {pdf_path.name}: {e}", file=sys.stderr)
        return []

    current_section = "General"
    current_consolidated = "unknown"

    for page_num, page in enumerate(doc, start=1):
        text = page.get_text("text").strip()
        if not text or len(text) < 30:
            continue

        section = detect_section(text)
        if section != "General":
            current_section = section
        consolidated = detect_consolidated(text)
        if consolidated != "unknown":
            current_consolidated = consolidated

        for chunk_text_str in chunk_text(text):
            chunk = {
                "chunk_id": f"{doc_id}_p{page_num:04d}_c{chunk_idx:03d}",
                "doc_id": doc_id,
                "company": company,
                "fiscal_year": fy,
                "doc_type": doc_type,
                "section": current_section,
                "page": page_num,
                "standalone_consolidated": current_consolidated,
                "text": chunk_text_str,
                "score": 0.0,
            }
            chunks.append(chunk)
            chunk_idx += 1

    doc.close()
    return chunks


def run():
    all_pdfs = sorted(CORPUS_ROOT.rglob("*.pdf"))
    # Keep only PDFs whose company folder (2nd part for Annual reports/X/file, 1st for X/file)
    # is one of the 10 target companies.
    ALLOWED_FOLDERS = set(COMPANY_ALIASES.keys())
    def _company_folder(p: Path) -> str:
        parts = p.relative_to(CORPUS_ROOT).parts
        return parts[1] if len(parts) > 2 else parts[0]
    pdf_paths = [p for p in all_pdfs if _company_folder(p) in ALLOWED_FOLDERS]
    skipped = len(all_pdfs) - len(pdf_paths)
    if skipped:
        skipped_folders = {_company_folder(p) for p in all_pdfs if _company_folder(p) not in ALLOWED_FOLDERS}
        print(f"Skipping {skipped} PDFs from out-of-scope folders: {skipped_folders}")
    print(f"Parsing {len(pdf_paths)} PDFs…")

    combined_path = PARSED_DIR / "all_chunks.jsonl"
    total_chunks = 0
    docs_processed = 0
    company_counts: dict[str, int] = {}

    with open(combined_path, "w") as combined_f:
        for pdf_path in tqdm(pdf_paths, unit="pdf"):
            _, fy, doc_type, doc_id = parse_filename(pdf_path)
            out_path = PARSED_DIR / f"{doc_id}.jsonl"

            # Re-use cached parse if available
            if out_path.exists():
                with open(out_path) as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            combined_f.write(line + "\n")
                            total_chunks += 1
                            company = json.loads(line).get("company", "?")
                            company_counts[company] = company_counts.get(company, 0) + 1
                continue

            chunks = parse_pdf(pdf_path)
            if not chunks:
                print(f"  WARNING: 0 chunks from {pdf_path.name}", file=sys.stderr)
                continue

            with open(out_path, "w") as f:
                for chunk in chunks:
                    line = json.dumps(chunk, ensure_ascii=False)
                    f.write(line + "\n")
                    combined_f.write(line + "\n")
                    total_chunks += 1
                    company_counts[chunk["company"]] = company_counts.get(chunk["company"], 0) + 1

            docs_processed += 1

    print(f"\nDone. {total_chunks:,} total chunks from {len(pdf_paths)} PDFs.")
    print(f"Per-doc files: {PARSED_DIR}/")
    print(f"Combined: {combined_path}")
    print("\nChunks per company:")
    for company, count in sorted(company_counts.items()):
        print(f"  {company}: {count:,}")


if __name__ == "__main__":
    run()
