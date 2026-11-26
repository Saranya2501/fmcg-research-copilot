# P5 — Observability & Deployment

Owner: Irfan

Owns Langfuse tracing integration, the Streamlit entry point, and Docker
configuration. Tracing hooks support evaluation runs; an end-to-end scoring
runner and machine-readable final evaluation results are not included in the
current repository. See [P1 evaluation material](../p1-eval/README.md).

## Required data and credentials

Download both the indexes and full parsed chunks from the
[shared Drive folder](https://drive.google.com/drive/folders/1-WKMvaOx8v3jJAcwN_jSKkMa3AHC1OR-).
From the repository root, the default app requires:

```text
p4-agent/p3_retrieval/index/bm25.pkl
p4-agent/p3_retrieval/index/faiss.index
p4-agent/p3_retrieval/index/chunk_ids.json
p4-agent/p3_retrieval/parsed/all_chunks.jsonl
```

Use all four files from the same rebuild. The tracked retrieval source is already
included; the chunk sample cannot substitute for the full corpus. The original
source PDFs are not needed to query an existing complete bundle.

Create `p5-deployment/.env` from `.env.example` and configure a model before
starting. For IITK use the [institute API instructions](#iitk-institute-api).
Authorized API credentials and CA certificates are supplied separately; public
code and data do not grant endpoint access. Never put API keys in Git or the
public submission folder. Langfuse credentials are optional for answering, but
are required to export real query traces.

## Run with Docker

Install and start Docker Desktop. Download the data and configure
`p5-deployment/.env` first. For IITK certificates, place the LLM and embedding CA
files in `p5-deployment/certs/` on the host. Compose mounts that directory at
`/app/p5-deployment/certs/` inside the container. Set certificate values in `.env`
to the container paths, for example:

```dotenv
LLM_CA_CERT=/app/p5-deployment/certs/llm-ca.crt
CACERT_PATH=/app/p5-deployment/certs/vm02-ca.crt
```

Use the actual supplied filenames (the LLM filename above is illustrative).
Host paths such as `/Users/...` do not resolve inside the container. Then run
from the repository root:

```bash
docker compose -f p5-deployment/docker-compose.yml up --build -d
```

Open http://localhost:8501. The app uses the latest supplied P4 Python query runner.
It includes a chat input, conversation history for the current session, and a New chat
button. Research needs a configured model and the complete P3 source-data layout.
Until those are available, the app shows setup information rather than fabricated answers.

## Saved conversations

Every new conversation gets a UUID stored with its history. Messages, their roles,
and UTC timestamps are stored in `p5-deployment/data/chat_history.sqlite3`.
The sidebar's Chat history lists chats using the first six words of their first
user message as the title. Click a title to reopen and continue a chat, including after restarting
the app. New chat creates a separate conversation and keeps the previous history.
Empty conversations are hidden from history, keeping one New chat action in the sidebar.
Existing in-session messages are saved when the updated app first loads.

Set `CHAT_HISTORY_DB` to override the database path. Local history is excluded from
Git and Docker builds. Docker Compose keeps it in the `chat-history` volume.
This is a single-user local history store: all app sessions can see the saved chats.
Authenticated per-user ownership is needed before sharing the app publicly.

View logs or stop the app:

```bash
docker compose -f p5-deployment/docker-compose.yml logs -f
docker compose -f p5-deployment/docker-compose.yml down
```

## Run locally

From the repository root, using Python 3.11 or later:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r p5-deployment/requirements.txt
cp p5-deployment/.env.example p5-deployment/.env
# Configure .env and download the data before the next command.
python -m streamlit run p5-deployment/app.py
```

Edit `p5-deployment/.env` to configure the model, rate limits, the optional history
path, and Langfuse credentials. The filename must be `.env`, not `env`. The app
loads this file automatically; existing environment
variables take priority. Restart Streamlit after changing configuration. `.env` is
excluded from Git.

## IITK institute API

For the full app, keep both LLM and embedding settings in
`p5-deployment/.env`. The separate `p3-retrieval/.env` is for standalone P3 usage.
Replace every placeholder below with the values assigned by IITK:

```dotenv
LLM_BASE_URL=
LLM_TARGET=api
LLM_API_BASE_URL=https://YOUR-IITK-HOST:PORT/v1
LLM_API_KEY=YOUR_AUTHORIZED_LLM_KEY
LLM_MODEL=Qwen/Qwen3-8B
LLM_CA_CERT=/absolute/path/to/the/supplied/llm-ca.crt

# Optional remote query embeddings; these use separate access credentials.
IITK_EMBED_URL=https://103.42.50.41:1035/v1/embeddings
IITK_EMBED_KEY=YOUR_AUTHORIZED_EMBEDDING_KEY
CACERT_PATH=/absolute/path/to/the/supplied/vm02-ca.crt
```

Leave `LLM_BASE_URL` empty: a nonempty value selects the generic compatible
connection instead of institute mode. That generic mode reads `LLM_TLS_CA_CERT`,
not `LLM_CA_CERT`. Use the API base URL ending in `/v1`, without appending
`/chat/completions`. Confirm the LLM port and certificate with the endpoint
owner; the embedding CA is not automatically valid for the LLM endpoint.

For local runs, absolute certificate paths must point to existing files on your
machine. For Docker, use the mounted container paths documented above. Keep the
example's cache/log/lock paths from `.env.example`, and run from the repository
root. Existing exported environment variables take precedence over `.env`;
restart Streamlit after configuration changes.

Remote embeddings are optional. When the embedding URL/key are absent, P3 uses
the local `BAAI/bge-small-en-v1.5` model. The `BAAI/bge-reranker-base` reranker
always loads locally in this implementation. First use may download model
weights; allow network access and startup time. An embedding API failure also
triggers local embedding fallback.

If the app reports a research failure, check the selected provider/model and
`p5-deployment/data/logs/llm_calls.jsonl`. `target=local` means an Ollama connection
was selected. `CERTIFICATE_VERIFY_FAILED` means the endpoint's certificate chain
could not be verified with the configured CA. The generic P4 failure message
intentionally hides raw exception details. Passing offline tests does not verify
live endpoint availability; confirm a real cited answer and its trace separately.

## Connect your API

For an OpenAI-compatible Chat Completions provider, set just these three values
in `p5-deployment/.env` and restart Streamlit:

```dotenv
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_API_KEY=your-provider-key
LLM_MODEL=your-provider-model-id
```

Use your provider's base URL and a model available to your account. A nonempty
`LLM_BASE_URL` automatically selects this connection, even if an older `.env`
still says `LLM_TARGET=local`. No institute CA certificate or Qwen-specific
thinking flags are sent. HTTPS verification stays enabled. Langfuse, retries,
the model-call cache, and final-response caching continue to work.

The provider/model must support Chat Completions. JSON mode is enabled by default;
set `LLM_JSON_MODE=false` if that server does not support `response_format`.
P2 still validates the returned JSON and applies its repair loop. This does not
claim native compatibility with every vendor's distinct API protocol.

Leave `LLM_BASE_URL` blank to retain `LLM_TARGET=local` (Ollama) or `LLM_TARGET=api`
(institute endpoint and certificate). `LLM_TLS_CA_CERT` is an optional custom CA
for a generic endpoint, independent of the institute's `LLM_CA_CERT`.
The API connection does not replace P3's required parsed corpus/index files.

## Langfuse tracing

The app uses Langfuse Python SDK 5.2.0 (for Langfuse Cloud / platform v4).
Fill `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_BASE_URL` in
`p5-deployment/.env`, then restart Streamlit. Docker Compose also passes this
optional file into the container without baking credentials into the image.

Each accepted chat turn creates a `process-chat-turn` trace, with a child
`generate-response` span. P4's gatekeeper, planner, query writer, analyst, writer
and critic have nested agent observations; retrieval has a retriever observation.
P2 uses Langfuse's native OpenAI wrapper for actual model generations and usage.
The conversation UUID becomes the Langfuse session ID,
grouping turns from reopened chats. Rate-limited messages and UI reruns do not
create traces. The optional preview backend remains available with
`CHAT_BACKEND=preview` and does not invent model usage or cache preview replies.

The client is reused across Streamlit reruns and exports in the background.
Missing credentials or `LANGFUSE_TRACING_ENABLED=false` disable tracing. Trace
setup/export problems do not retry or duplicate a chat operation. Application
failures are marked with a generic error status without exporting raw exception
text. The exporter masks common email addresses, sk-/pk- keys, and bearer tokens.
This is basic masking, not a comprehensive detector for all sensitive content.
Credentials, SQLite paths, and the entire application state are never trace inputs.

Use Traces for individual turns and Sessions for complete conversations.
`LANGFUSE_ENVIRONMENT` can distinguish development from deployment runs.
Restart the app after changing keys or tracing configuration.

Run the offline tracing checks:

```bash
.venv/bin/python -m unittest discover -s p5-deployment/tests -v
PYTHONPATH=p4-agent .venv/bin/python -m pytest p4-agent/tests p4-agent/integration/tests -q
.venv/bin/python p4-agent/integration/p2_agents/tests/test_agents.py
```

## Response cache and answer trace links

Each new assistant message saves its Langfuse trace ID and URL, cache status,
latency in milliseconds, and citation payload alongside its answer. The **View trace**
button remains available when reopening a saved conversation. Existing history is
migrated automatically without deleting messages; older answers without a recorded
trace do not get invented links. Tracing can still be disabled independently.

Exact responses are cached in a `response_cache` table in the same SQLite database.
`CHAT_CACHE_ENABLED=true` enables lookup and `CHAT_CACHE_TTL_SECONDS=3600` gives
entries a one-hour lifetime. Expired entries are removed on lookup or subsequent
writes. Disable caching with `CHAT_CACHE_ENABLED=false`, or pass
`bypass_cache=True` to `process_chat_turn()` for scored evaluation runs (no reads or writes).

Keys include the exact question (outer whitespace removed), prior message roles,
content and citations, filters, provider/model, generation settings, prompt version,
corpus version, and pipeline version. Timestamps and conversation IDs do not change
answers, so they are excluded. Identical standalone requests can share a cached
answer; a follow-up with different history cannot. This cache follows the app's
existing single-user deployment model and must be partitioned by authenticated
owner/tenant before a multi-user deployment.

Every accepted turn starts a fresh trace, including cache hits; a hit does not reuse
the original trace link or create a generation observation. Trace metadata includes
`cache_hit`, `cache_status`, `latency_ms`, and the explicit response configuration.
Cached answers retain their citations and show a small Cached response label.
Cache read/write failures fall back to normal response processing.

The optional **preview adapter bypasses caching completely**. Failed, blank, and
non-cacheable results are never stored. `generate_response()` delegates to the P4
bridge, which marks only complete, cited, critic-approved answers as cacheable.
Cache keys fingerprint the actual P2 prompt/settings files, P4 and bridge code,
model endpoint, and P3 file sizes/modification times. Replace data atomically and
restart after changing packages or model configuration.
The cache is tested through the supplied P4 runner with scripted model replies and retrieval.

## Latest P4 integration

`agent_bridge.py` calls the entry point documented by the new P4 package:
`p4-agent/integration/runtime.py::run_query(question, p2_path, p3_path, llm=...)`.
It does not invoke the old P4 graph rewrite. The supplied P4/P2 source is preserved;
the adapter loads P2 into an isolated import namespace, avoiding collisions with
flat module names such as `config`, `schemas` and `agents`.

P2 defaults to `p4-agent/integration/p2_agents`; override with `P2_PACKAGE_PATH`.
Retrieval defaults to `p4-agent/p3_retrieval` inside the supplied P4 package;
override with `P3_RAG_PATH`. The separate top-level `p3-retrieval` folder is not
used by P5's default configuration, dependencies, or container.
It must contain `retrieve.py`, `index/bm25.pkl`, `index/faiss.index`,
`index/chunk_ids.json`, and `parsed/all_chunks.jsonl`. Download and extract the
indexes and parsed chunks from the shared Drive folder into this layout. A chunk
sample is not a replacement for the full parsed corpus.

The adapter injects the saved conversation history and last company/metric/year
context into P2's gatekeeper, then saves the new resolved context with the answer.
It normalizes P4's `refused` and `partial_validation` variants to the P5 response
contract. Partial, unsupported, missing-evidence or invalid-citation responses
are not cached. Citation document/page values come from retrieved evidence.
Actual model-call usage, cache hits and JSON attempts/repairs are saved per turn;
scored runs bypass both the final-response cache and P2's model cache.
The runtime's calculator call is wrapped in memory for tracing and tool counting;
its source file is unchanged. The adapter bounds expression length/complexity and
allows the prompt contract's arithmetic rather than unbounded exponentiation.

P5 enforces a configurable cumulative token allowance (`AGENT_TOKEN_BUDGET`,
default 6000) across model calls, including JSON repairs. The input estimate is
approximate; actual reported usage is checked after each call and further work
stops when the budget is exhausted. Cache hits have zero new billed token usage.
Model/client errors are shown as a controlled partial response.

The supplied `run_query` helper is a single-answer path. It does not expose the
separate LangGraph workflow, brief export, or critic revision loop; P5 does not
claim those are integrated. Gold-set scoring and full live retrieval verification
remain separate work. Received notebook/archive/reference files are not runtime
dependencies and are not executed by the application.

## Rate limit

The chat accepts 5 messages per rolling 60 seconds per Streamlit session. Rejected
messages do not enter the conversation or invoke the agent. New chat clears history
but preserves the limit. Configure it before launching:

```bash
export CHAT_RATE_LIMIT=5
export CHAT_RATE_WINDOW_SECONDS=60
streamlit run p5-deployment/app.py
```

Both values must be positive integers. This session limit can reset on a new browser
session or server restart. A shared authenticated user limit will be needed for a
public deployment across sessions or servers.

## Files

- `app.py` — Streamlit chat interface with session history and an explicit preview status
- `requirements.txt` — dependencies for the current Streamlit starter
- `tracing.py` — session-aware tracing, masking, and optional client setup
- `response_cache.py` — exact cache keys, persistent responses, expiry and clearing
- `agent_bridge.py` — latest P4 runner adapter, response normalization and usage collection
- `p4_loader.py` — isolated imports of the received flat P2 source
- `api_connection.py` — common API configuration and OpenAI-compatible transport
- `Dockerfile` — Python 3.11 image with a non-root user and health check
- `docker-compose.yml` — app service available locally on port 8501
- `../.dockerignore` — excludes credentials and generated data from the build context

## Live-run verification

Install the complete matching data bundle from Drive and configure an Ollama,
institute API, or compatible-provider target. Docker mounts the P3 index and parsed corpus read-only; configure certificate
paths inside the container and use `host.docker.internal` for Ollama on a Mac host.
Then verify real research answers before running the approved gold evaluation set.
