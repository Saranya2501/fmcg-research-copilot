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

## Quick start (P3 retrieval)

See `p3-retrieval/INTEGRATION.md` for full setup, interface contract, and corpus status.

```bash
cd p3-retrieval
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.template .env   # fill in IITK_API_KEY and group base URL
```

Index files (too large for git) are shared separately — place them at `p3-retrieval/index/`.

## Gates

| Gate | Date | Description |
|---|---|---|
| C | 14 Nov | Retrieval measured |
| D | 18 Nov | Full eval run through agent with traces |
| — | 20 Nov | Code freeze |
| — | 21 Nov | Final eval on frozen code |
| — | 25 Nov | Report due |
| — | 26 Nov | Demo |
