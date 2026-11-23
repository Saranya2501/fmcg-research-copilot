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

## Run the agent

Run the commands below from the repository root.

### 1. Download the research data

Get the prebuilt index and its matching parsed corpus from the team's shared Google Drive. The project uses the Drive folder layout `My Drive/fmcg-research-copilot/p3-retrieval/`. Ask Saranya (P3 retrieval) for the shared folder if you need access.

| Download from the P3 Drive folder | Place in your local checkout |
|---|---|
| `index/bm25.pkl` | `p4-agent/p3_retrieval/index/bm25.pkl` |
| `index/faiss.index` | `p4-agent/p3_retrieval/index/faiss.index` |
| `index/chunk_ids.json` | `p4-agent/p3_retrieval/index/chunk_ids.json` |
| `parsed/all_chunks.jsonl` | `p4-agent/p3_retrieval/parsed/all_chunks.jsonl` |

If you receive `index_bundle.zip`, extract it into `p4-agent/p3_retrieval/`. It contains the three files under `index/`. Download `all_chunks.jsonl` separately. Both run options use these same local paths, and Git ignores both data directories.

### 2. Configure the app once

Place the environment file inside `p5-deployment/`, beside `app.py`, and name it exactly `.env`. The full path within a checkout is `fmcg-research-copilot/p5-deployment/.env`. Docker Compose and the local Python app both load this file automatically.

If you received a configured environment file, copy it to that location. For example, if it is saved as `fmcg.env` in Downloads, run this from the repository root:

```bash
cp -n ~/Downloads/fmcg.env p5-deployment/.env
```

If you are starting from the template, run the following command and then edit `p5-deployment/.env` with your credentials. Both copy commands preserve an existing `.env`.

```bash
cp -n p5-deployment/.env.example p5-deployment/.env
```

#### Institute research setup

Set these values in `p5-deployment/.env`. Place both supplied certificate files in `p5-deployment/certs/`.

| Variable | Value to use | Purpose |
|---|---|---|
| `IITK_API_BASE` | Institute-provided chat API base URL | Selects the institute chat endpoint. |
| `IITK_API_KEY` | Your institute chat API key | Authenticates model requests. |
| `LLM_TLS_CA_CERT` | `p5-deployment/certs/vm07-ca.crt` | Verifies the chat endpoint. This path is relative to the repository root. |
| `IITK_EMBED_URL` | Institute embedding endpoint from the template | Generates query embeddings for research. |
| `IITK_EMBED_KEY` | Your institute embedding API key | Authenticates embedding requests. |
| `CACERT_PATH` | `../../p5-deployment/certs/vm02-ca.crt` | Verifies the embedding endpoint. This path is relative to the retrieval module. |
| `RAG_RERANKER_ENABLED` | `false` for the standard installation | Set to `true` if you install the optional local reranker. |

<details>
<summary>Other model providers and optional settings</summary>

For another model provider, leave `IITK_API_BASE` empty. For a provider with a publicly trusted certificate, also clear the institute certificate path in `LLM_TLS_CA_CERT`.

| Variable | When to use it | Value or example |
|---|---|---|
| `LLM_BASE_URL` | OpenAI-compatible provider | Your provider’s API base URL, such as `https://api.groq.com/openai/v1`. |
| `LLM_API_KEY` | OpenAI-compatible provider or explicit institute API mode | Your provider-issued chat key. |
| `LLM_MODEL` | Hosted model selection | Your provider’s model ID. The institute configuration defaults to `Qwen/Qwen3-8B`. |
| `LLM_JSON_MODE` | Compatible provider | `true` in the template. Set to `false` if the provider lacks JSON response mode. |
| `LLM_TARGET` | Model selection without a base URL override | `local` for Ollama or `api` for explicit institute API mode. |
| `LLM_LOCAL_BASE_URL`, `LLM_LOCAL_MODEL` | Ollama | `http://localhost:11434/v1` and `qwen3:8b`. From Docker on macOS use `http://host.docker.internal:11434/v1`. |
| `LLM_API_BASE_URL`, `LLM_CA_CERT` | Explicit institute API mode | Institute chat API base URL and path to the supplied chat CA certificate. |
| `CHAT_BACKEND`, `CHAT_RETRIEVAL_ENABLED` | Research mode | The template uses `agent` and `true`. Set retrieval to `false` for direct chat. |
| `AGENT_TOKEN_BUDGET` | Research turn budget | `24000` in the template, counting input and output across model calls. |
| `CHAT_RATE_LIMIT`, `CHAT_RATE_WINDOW_SECONDS` | Per-session message limit | The template allows `5` messages per `60` seconds. |
| `CHAT_CACHE_ENABLED`, `CHAT_CACHE_TTL_SECONDS` | Final-answer cache | `true` and `3600` seconds in the template. |
| `LLM_CACHE`, `LLM_CACHE_PATH` | Model-call cache | `1` enables caching. The template stores it at `p5-deployment/data/llm_cache.sqlite`. |
| `LLM_LOG_PATH`, `LLM_LOCK_PATH` | Model-call logging and locking | The template uses `p5-deployment/data/logs/llm_calls.jsonl` and `p5-deployment/data/llm_api.lock`. |
| `CHAT_HISTORY_DB` | Custom conversation database | Optional absolute path. The default is `p5-deployment/data/chat_history.sqlite3`. |
| `REDIS_URL` | Local Redis with Search support | Leave unset for standalone Python. Compose supplies `redis://redis:6379/0`. |
| `P3_RAG_PATH`, `P2_PACKAGE_PATH` | Custom retrieval or prompting package location | Optional absolute paths. The project uses `p4-agent/p3_retrieval/` and `p4-agent/integration/p2_agents/` by default. |
| `INSTALL_LOCAL_MODELS` | Optional Docker build | Set to `true` and use the build command in [Optional local models](#optional-local-models). |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` | Langfuse tracing | Your project’s public key, secret key, and regional or self-hosted URL. |
| `LANGFUSE_TRACING_ENABLED`, `LANGFUSE_ENVIRONMENT` | Tracing controls | The template uses `true` and `development`. |

</details>

### 3. Start the app

**With Docker** — start Docker with Compose v2.24 or later and run:

```bash
docker compose up --build -d
```

Compose starts the app and Redis. Use `docker compose down` to stop them.

**Without Docker** — with Python 3.11 or later, install dependencies once (macOS/Linux):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Then start the app with this command:

```bash
.venv/bin/python -m streamlit run p5-deployment/app.py
```

Leave `REDIS_URL` unset for a standalone local run. Press Ctrl+C to stop the app.

Open [FMCG Research Copilot](http://localhost:8501) after starting either version.

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

## Gates

| Gate | Date | Description |
|---|---|---|
| C | 14 Nov | Retrieval measured |
| D | 18 Nov | Full eval run through agent with traces |
| — | 20 Nov | Code freeze |
| — | 21 Nov | Final eval on frozen code |
| — | 25 Nov | Report due |
| — | 26 Nov | Demo |
