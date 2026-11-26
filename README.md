# FMCG Competitive Research Copilot

Multi-agent RAG system for financial and competitive analysis of India-listed FMCG companies using public filings.

**Programme:** IITK Executive PGP in Generative AI and Agentic AI — Capstone Track B  
**Model:** Qwen3-8B on the institute's hosted endpoint

## Run the agent

Run these steps from the repository root. Use Docker with Compose v2.24 or later, or Python 3.11 or later.

### 1. Add the research data

Get the matching index bundle and `all_chunks.jsonl` from the team's Google Drive folder `My Drive/fmcg-research-copilot/p3-retrieval/`. Extract `index_bundle.zip` into `p4-agent/p3_retrieval/` and put `all_chunks.jsonl` in its `parsed/` directory. The four files should be here:

```text
p4-agent/p3_retrieval/
├── index/
│   ├── bm25.pkl
│   ├── chunk_ids.json
│   └── faiss.index
└── parsed/
    └── all_chunks.jsonl
```

### 2. Add your credentials

Save the team's configured environment file as `p5-deployment/.env`. If you need to create one, copy the template:

```bash
cp -n p5-deployment/.env.example p5-deployment/.env
```

Fill in `LLM_BASE_URL` (without `/chat/completions`), `LLM_API_KEY`, `LLM_MODEL`, `IITK_EMBED_URL`, and `IITK_EMBED_KEY`. Keep `RAG_RERANKER_ENABLED=false` for the standard setup.

If you use the institute endpoints, put the supplied CA files in `p5-deployment/certs/` and set `LLM_CA_CERT=p5-deployment/certs/vm07-ca.crt` and `CACERT_PATH=../../p5-deployment/certs/vm02-ca.crt`.

### 3. Start the app

**Docker.** Start Docker and run:

```bash
docker compose up --build -d --remove-orphans
```

Compose runs the app with SQLite for chat history. The command also removes the old Redis container if it exists for this Compose project. Run `docker compose logs -f` to view logs or `docker compose down` to stop the app.

**Local Python (macOS/Linux).** Leave `REDIS_URL` unset and run:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run p5-deployment/app.py
```

Open [FMCG Research Copilot](http://localhost:8501) and try asking how HUL's revenue changed in FY24. Press Ctrl+C to stop the local Python run.

<details>
<summary>Optional settings</summary>

| Variable | When to use it | Value or example |
|---|---|---|
| `LLM_JSON_MODE` | Provider without JSON response mode | `true` in the template. Set to `false` if unsupported. |
| `CHAT_BACKEND` | Research mode | Defaults to `agent`. |
| `AGENT_TOKEN_BUDGET` | Research turn budget | `24000` in the template, counting input and output across model calls. |
| `CHAT_RATE_LIMIT`, `CHAT_RATE_WINDOW_SECONDS` | Per-session message limit | The template allows `5` messages per `60` seconds. |
| `CHAT_CACHE_ENABLED`, `CHAT_CACHE_TTL_SECONDS` | Final-answer cache | `true` and `3600` seconds in the template. |
| `LLM_CACHE`, `LLM_CACHE_PATH` | Model-call cache | `1` enables caching. The template stores it at `p5-deployment/data/llm_cache.sqlite`. |
| `LLM_LOG_PATH`, `LLM_LOCK_PATH` | Model-call logging and locking | The template uses `p5-deployment/data/logs/llm_calls.jsonl` and `p5-deployment/data/llm_api.lock`. |
| `CHAT_HISTORY_DB` | Custom conversation database | Optional absolute path. The default is `p5-deployment/data/chat_history.sqlite3`. |
| `REDIS_URL` | Local Redis with Search support | Optional for direct Python runs. Leave unset for standard setup. |
| `P3_RAG_PATH`, `P2_PACKAGE_PATH` | Custom retrieval or prompting package location | Optional absolute paths. The project uses `p4-agent/p3_retrieval/` and `p4-agent/integration/p2_agents/` by default. |
| `INSTALL_LOCAL_MODELS` | Optional Docker build | Set to `true` and use the build command in [Optional local models](#optional-local-models). |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` | Langfuse tracing | Your project’s public key, secret key, and regional or self-hosted URL. |
| `LANGFUSE_TRACING_ENABLED`, `LANGFUSE_ENVIRONMENT` | Tracing controls | The template uses `true` and `development`. |

</details>

### Optional local models

The runtime requirements exclude PDF parsers, index-building scripts, pytest,
LangGraph, and document-export tooling. FAISS, NumPy and BM25 remain necessary to
query the existing indexes. Query embeddings still require an embedding service.
The base install excludes sentence-transformers and PyTorch.

If local query embeddings or BGE reranking are needed, install
`p5-deployment/requirements-local-models.txt` instead. For Docker, add
`INSTALL_LOCAL_MODELS=true` to `p5-deployment/.env` and run:

```bash
docker compose --env-file p5-deployment/.env up --build -d
```

Set `RAG_RERANKER_ENABLED=true` only when those optional packages are installed.
Local models download on first use. An embedding API failure can only fall back
to local embeddings when those packages are installed.
See [deployment details](p5-deployment/README.md) for model and tracing options.

## Team

| Workstream | Owner | Current location |
|---|---|---|
| P1 — Spec, eval & safety | Yogesh | Git history |
| P2 — Prompting & API client | Himanshu | `p4-agent/integration/p2_agents/` |
| P3 — Retrieval (RAG) | Saranya | `p4-agent/p3_retrieval/` |
| P4 — Agent & tools | Rohit | `p4-agent/` |
| P5 — Observability & deployment | Irfan | `p5-deployment/` |

## Companies covered

HUL · ITC · Nestle India · Dabur · Britannia · Marico · GCPL · Colgate-Palmolive India · Tata Consumer Products · Emami

## Gates

| Gate | Date | Description |
|---|---|---|
| C | 14 Nov | Retrieval measured |
| D | 18 Nov | Full eval run through agent with traces |
| — | 20 Nov | Code freeze |
| — | 21 Nov | Final eval on frozen code |
| — | 25 Nov | Report due |
| — | 26 Nov | Demo |
