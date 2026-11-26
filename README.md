# FMCG Competitive Research Copilot

Multi-agent RAG system for financial and competitive analysis of India-listed FMCG companies using public filings.

**Programme:** IITK Executive PGP in Generative AI and Agentic AI — Capstone Track B  
**Model:** Qwen3-8B on the institute's hosted endpoint

## Team

| Workstream | Owner | Folder |
|---|---|---|
| P1 — Spec, eval & safety | Yogesh | `p1-eval/` |
| P2 — Prompting & API client | Himanshu | `p2-prompting/` |
| P3 — Retrieval (RAG) | Saranya | `p3-retrieval/` |
| P4 — Agent & tools | Rohit | `p4-agent/` |
| P5 — Observability & deployment | Irfan | `p5-deployment/` |

## Companies covered

HUL · ITC · Nestle India · Dabur · Britannia · Marico · GCPL · Colgate-Palmolive India · Tata Consumer Products · Emami

## Run the full application

Use Python 3.11 or later. Run these commands in a terminal (macOS/Linux):

```bash
git clone https://github.com/Saranya2501/fmcg-research-copilot.git
cd fmcg-research-copilot
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r p5-deployment/requirements.txt
cp p5-deployment/.env.example p5-deployment/.env
```

Before starting, download the data described below and configure the model in
`p5-deployment/.env`. See [IITK configuration](p5-deployment/README.md#iitk-institute-api)
for the LLM endpoint, credentials, CA certificate, and optional embedding API.
Public access to this repository does not provide access to IITK inference;
each user needs authorized credentials and the supplied CA certificates.
Keep API keys out of Git and the public submission folder.

Then start the application from the repository root:

```bash
python -m streamlit run p5-deployment/app.py
```

Open http://localhost:8501. Restart Streamlit after changing `.env`. First-use
retrieval downloads the local reranker and, when needed, the embedding model;
allow network access and additional startup time.

## Download the retrieval data

The indexes and full parsed chunk corpus are stored separately in the
[shared submission folder on Google Drive](https://drive.google.com/drive/folders/1-WKMvaOx8v3jJAcwN_jSKkMa3AHC1OR-).
Download and extract the matching index and parsed-data bundle into this layout
for the default Streamlit application:

```text
p4-agent/p3_retrieval/
  retrieve.py                 # already in Git
  index/
    bm25.pkl
    faiss.index
    chunk_ids.json
  parsed/
    all_chunks.jsonl
```

All four data files are required and must come from the same rebuild. An index
archive alone or the tracked chunk sample cannot replace `all_chunks.jsonl`.
The locally verified bundle on 26 November 2026 contained 117,194 chunks,
482 distinct document IDs, and no duplicate chunk IDs. These counts describe
the local bundle; the Drive upload must be checked against it.

For standalone P3 retrieval, put the same files under `p3-retrieval/index/` and
`p3-retrieval/parsed/` instead. See the [P3 guide](p3-retrieval/INTEGRATION.md).
The default Streamlit app uses `p4-agent/p3_retrieval/`; `P3_RAG_PATH` can override
that location for local runs. Docker Compose mounts the bundled P4 location.

## Implementation and verification

The Streamlit application calls `p4-agent/integration/runtime.py::run_query`
through P5's adapter. P2 agents and prompts are included under
`p4-agent/integration/p2_agents/`. The separate P4 LangGraph implementation is
also included, but is not the execution path used by Streamlit.

See the [P5 guide](p5-deployment/README.md) for Docker, tracing, caching,
conversation history, and offline test commands. The local review on
26 November 2026 passed 36 P5 tests, 20 P4/integration tests, and 28 P2 checks;
these offline results do not establish live IITK connectivity or answer accuracy.

The [P1 guide](p1-eval/README.md) identifies the 100-question dataset and the
available retrieval evaluation script. An end-to-end scoring runner and its
machine-readable final results are not included in the current repository.

## Project milestones (original schedule)

| Gate | Date | Description |
|---|---|---|
| C | 14 Nov | Retrieval measured |
| D | 18 Nov | Full eval run through agent with traces |
| — | 20 Nov | Code freeze |
| — | 21 Nov | Final eval on frozen code |
| — | 25 Nov | Report due |
| — | 26 Nov | Demo |
