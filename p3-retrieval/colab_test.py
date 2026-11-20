# ============================================================
# FMCG Research Copilot — P3 RAG: Colab Test Script
# ============================================================
# How to use in Google Colab:
#
#   Step 1. Upload your p3-retrieval folder to Google Drive at:
#           MyDrive/fmcg-research-copilot/p3-retrieval/
#           (Must include: index/, parsed/, retrieve.py, requirements.txt)
#
#   Step 2. Copy this file into a Colab notebook (File → Upload notebook)
#           OR paste each section into separate cells.
#
#   Step 3. Run all cells top to bottom.
# ============================================================


# ── CELL 1: Install dependencies ────────────────────────────
# (Run once per session — takes ~2 min on first run)

import subprocess, sys

packages = [
    "faiss-cpu",
    "sentence-transformers",
    "rank-bm25",
    "python-dotenv",
    "httpx",
    "tqdm",
]
subprocess.check_call([sys.executable, "-m", "pip", "install", "-q"] + packages)
print("Packages installed.")


# ── CELL 2: Set IITK API credentials (optional but recommended) ──────────────
# If you have the IITK embedding API key, set it here.
# retrieve() will use the API (fast: ~1s) instead of the local model (~15s cold start).
# Both use the same model (bge-small-en-v1.5) so results are identical.
# Leave IITK_EMBED_KEY empty to fall back to local SentenceTransformer.

import os
os.environ["IITK_EMBED_URL"] = "https://103.42.50.41:1035/v1/embeddings"
os.environ["IITK_EMBED_KEY"] = ""   # ← paste your key from shared-embedding-key.txt
os.environ["CACERT_PATH"]    = ""   # ← paste full path to vm02-ca.crt, or leave empty to skip cert verify


# ── CELL 3: Mount Google Drive and set paths ─────────────────

try:
    from google.colab import drive
    drive.mount("/content/drive")
    IN_COLAB = True
except ImportError:
    IN_COLAB = False
    print("Not in Colab — running locally.")

import sys
from pathlib import Path

if IN_COLAB:
    # Adjust this path if you placed the folder elsewhere in your Drive
    P3_DIR = Path("/content/drive/MyDrive/fmcg-research-copilot/p3-retrieval")
else:
    # Local: assumes you are running from the repo root
    P3_DIR = Path(__file__).resolve().parent

if not P3_DIR.exists():
    raise FileNotFoundError(f"p3-retrieval not found at {P3_DIR}. Check Drive path above.")

sys.path.insert(0, str(P3_DIR))
print(f"Using P3 at: {P3_DIR}")
print(f"  index dir:  {P3_DIR / 'index'} — exists: {(P3_DIR / 'index').exists()}")
print(f"  parsed dir: {P3_DIR / 'parsed'} — exists: {(P3_DIR / 'parsed').exists()}")


# ── CELL 4: Override RAG_DIR so retrieve.py finds index/parsed ──
# retrieve.py uses Path(__file__).parent — patch it after import
# by setting the module-level RAG_DIR to point to P3_DIR.

import importlib, types

# Import and immediately patch path constants before first use
import retrieve as _r
_r.RAG_DIR    = P3_DIR
_r.INDEX_DIR  = P3_DIR / "index"
_r.PARSED_DIR = P3_DIR / "parsed"

from retrieve import retrieve, get_table, _load_models, _load_index

print("Loading index (first time takes ~15–30s to download the reranker model)…")
_load_models()
_load_index()

# Count chunks in memory
from retrieve import _chunk_map
print(f"Index loaded: {len(_chunk_map):,} chunks ready.")


# ── CELL 5: Search helper — pretty-prints results ────────────

def search(
    query: str,
    company: str = None,
    fiscal_year: str = None,
    doc_type: str = None,
    section: str = None,
    k: int = 5,
    show_text_chars: int = 400,
):
    """
    Run a retrieval query and display results.

    Args:
        query:        Natural language question.
        company:      Filter by company name, e.g. "HUL", "Dabur", "ITC".
        fiscal_year:  Filter by FY, e.g. "FY24", "FY23".
        doc_type:     Filter by doc type: "annual_report", "quarterly_results",
                      "investor_presentation".
        section:      Filter by section: "P&L", "Balance Sheet", "MD&A",
                      "Notes to Accounts", "Segment Results", "Cash Flow".
        k:            Number of results to return (default 5).
        show_text_chars: How many chars of chunk text to show (default 400).
    """
    filters = {}
    if company:      filters["company"]     = company
    if fiscal_year:  filters["fiscal_year"] = fiscal_year
    if doc_type:     filters["doc_type"]    = doc_type
    if section:      filters["section"]     = section

    print(f"\n{'='*70}")
    print(f"QUERY: {query!r}")
    if filters:
        print(f"FILTERS: {filters}")
    print(f"{'='*70}")

    results = retrieve(query, k=k, filters=filters or None)

    if not results:
        print("No results returned.")
        return results

    for i, r in enumerate(results, 1):
        print(f"\n[{i}] score={r['score']:.3f}  |  {r['company']} · {r['fiscal_year']} · {r['doc_type']}")
        print(f"     chunk: {r['chunk_id']}")
        print(f"     page {r['page']}  section: {r['section']}  basis: {r.get('standalone_consolidated', '?')}")
        # Strip <<DATA>>…<<END DATA>> wrapper for readability
        raw = r["text"]
        if "<<DATA>>" in raw:
            raw = raw.split("<<DATA>>", 1)[1]
            if "<<END DATA>>" in raw:
                raw = raw.rsplit("<<END DATA>>", 1)[0]
            # Remove the source annotation line
            lines = raw.strip().splitlines()
            if lines and lines[0].startswith("[Source:"):
                raw = "\n".join(lines[1:]).strip()
        print(f"     ···\n     {raw[:show_text_chars].replace(chr(10), chr(10)+'     ')}")
        if len(raw) > show_text_chars:
            print(f"     … (+{len(raw)-show_text_chars} more chars)")

    return results


def show_table(doc_id: str, page: int = None, section_hint: str = None):
    """
    Extract and display a table from a document.
    Pass doc_id from a search() result.
    """
    result = get_table(doc_id, page=page, section_hint=section_hint)
    print(f"\nTABLE from {doc_id}  page={result.get('page')}  section={result.get('section')}")
    if result.get("low_confidence"):
        print("(low confidence — no [TABLE] marker found, showing text fallback)")
        print(result.get("text_fallback", "(no fallback)"))
        return result
    headers = result.get("headers", [])
    rows    = result.get("rows", [])
    if headers:
        col_w = [max(len(h), max((len(str(r[i])) for r in rows if i < len(r)), default=0))
                 for i, h in enumerate(headers)]
        fmt = "  ".join(f"{{:<{w}}}" for w in col_w)
        print("  " + fmt.format(*headers))
        print("  " + "  ".join("-" * w for w in col_w))
        for row in rows:
            padded = list(row) + [""] * (len(headers) - len(row))
            print("  " + fmt.format(*padded))
    return result


# ── CELL 6: Sample queries — edit and re-run as you like ─────

# Single-company metric lookup (UC1)
r1 = search(
    "HUL advertising and promotion expenses FY24",
    company="HUL", fiscal_year="FY24",
)

# Cross-company comparison (UC3/UC5)
r2 = search(
    "revenue from operations across FMCG companies FY24",
    fiscal_year="FY24", doc_type="annual_report",
)

# Management commentary (UC4)
r3 = search(
    "Dabur rural distribution strategy and growth outlook",
    company="Dabur",
)

# Show table from first result of r1 (if any)
if r1:
    show_table(r1[0]["doc_id"], page=r1[0]["page"], section_hint="P&L")


# ── CELL 7: Try your own query ───────────────────────────────
# Edit and run this cell as many times as you want.

MY_QUERY   = "Nestle India revenue and profit growth FY24"
MY_COMPANY = "Nestle India"   # or None to search all companies
MY_FY      = "FY24"           # or None

results = search(MY_QUERY, company=MY_COMPANY, fiscal_year=MY_FY, k=5)
