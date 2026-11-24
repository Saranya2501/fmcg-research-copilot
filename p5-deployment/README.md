# P5 — Observability & Deployment

Owner: Irfan

Owns Langfuse tracing integration, the evaluation runner with trace output, Streamlit entry point, and Docker configuration.

## Runtime dependencies

Use the repository-root [quick start](../README.md#run-the-agent) for Docker Compose
and direct Python startup with the existing index and supplied `.env`.
`requirements.txt` is runtime-only and does not include the P4 development list or
index-building dependencies. The default install excludes sentence-transformers
and PyTorch: configure `IITK_EMBED_URL` / `IITK_EMBED_KEY` and set
`RAG_RERANKER_ENABLED=false` in your existing `.env` as well as new installations.
FAISS, NumPy and BM25 are needed to search the prebuilt indexes.

For local query embeddings or reranking, install `requirements-local-models.txt`.
For Docker set `INSTALL_LOCAL_MODELS=true` in `.env` and build from the root with
`docker compose --env-file p5-deployment/.env up --build -d`.
These packages serve queries; they do not rebuild the index.

## Run with Docker

Install and start Docker Desktop, then run from the repository root:

```bash
docker compose -f p5-deployment/docker-compose.yml up --build -d
```

Open http://localhost:8501. The app uses the latest supplied P4 Python query runner.
It includes a chat input, conversation history for the current session, and a New chat
button. Research needs a configured model and the complete P3 source-data layout.
Until those are available, the app shows setup information rather than fabricated answers.

### Redis and future vector search

Compose also runs `redis:8.10.3`, which includes Redis Search and vector indexes.
Redis persists data in the `redis-data` volume with append-only persistence enabled.
The app waits for Redis to be healthy and uses `REDIS_URL=redis://redis:6379/0`
inside Compose. Port 6379 is exposed only on localhost for local development.
This local setup does not configure Redis authentication.

For a local Streamlit process, start only Redis and set
`REDIS_URL=redis://localhost:6379/0` in `.env`:

```bash
docker compose -f p5-deployment/docker-compose.yml up -d redis
```

`redis_connection.get_redis_client()` supplies a shared connection pool, verifies
connectivity and Redis Search availability, and preserves binary embedding bytes.
When `REDIS_URL` is unset, local runs do not require Redis. A configured but
unavailable Redis service stops app initialization with a setup error.
Existing SQLite history/caches and P3 retrieval are unchanged. Future vector
integration can use this client with `FT.CREATE` / `FT.SEARCH`; the index schema
and embedding dimensions should be chosen when that integration is implemented.
See the [Redis vector search documentation](https://redis.io/docs/latest/get-started/vector-database/).
`docker compose down` preserves Redis data; adding `-v` deletes Compose volumes.

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
streamlit run p5-deployment/app.py
```

Edit `p5-deployment/.env` to configure rate limits, the optional history path, and
Langfuse credentials. The app loads this file automatically; existing environment
variables take priority. Restart Streamlit after changing configuration. `.env` is
excluded from Git.

## Chat without retrieval

Set `CHAT_RETRIEVAL_ENABLED=false` in `p5-deployment/.env` and restart the app
to disable retrieval globally. This forces direct model chat, including for saved
research conversations. No source files, embedding model or reranker are loaded.
Model API configuration is still required.

With the default `CHAT_RETRIEVAL_ENABLED=true`, new chats use the research pipeline
and require the parsed corpus and indexes. Reopening a saved direct chat restores
its direct mode and uses the configured model API and recent chat history.

## Connect your API

P5 also accepts P2's `IITK_API_BASE` and `IITK_API_KEY` names. Set these in
`p5-deployment/.env`, along with `LLM_TLS_CA_CERT` pointing to `vm07-ca.crt`.
`IITK_API_BASE` takes precedence over `LLM_BASE_URL` and automatically activates
API chat; `LLM_MODEL` defaults to `Qwen/Qwen3-8B` for this endpoint. Existing
`LLM_*` configurations remain supported. For Docker set the certificate path to
`/app/p5-deployment/certs/vm07-ca.crt`.

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

`integrations/agent_bridge.py` calls the entry point documented by the new P4 package:
`p4-agent/integration/runtime.py::run_query(question, p2_path, p3_path, llm=...)`.
It does not invoke the old P4 graph rewrite. The supplied P4/P2 source is preserved;
the adapter loads P2 into an isolated import namespace, avoiding collisions with
flat module names such as `config`, `schemas` and `agents`.

P2 defaults to `p4-agent/integration/p2_agents`; override with `P2_PACKAGE_PATH`.
Retrieval defaults to `p4-agent/p3_retrieval` inside the supplied P4 package;
override with `P3_RAG_PATH`. The separate top-level `p3-retrieval` folder is not
used by P5's default configuration, dependencies, or container.
It must contain `retrieve.py`, `index/bm25.pkl`, `index/faiss.index`,
`index/chunk_ids.json`, and `parsed/all_chunks.jsonl`. The supplied index files
have been extracted from `index_bundle.zip` into P4's `index/`. A chunk sample is not a
replacement for the full parsed corpus.

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

- `app.py` — thin Streamlit entry point; loads environment settings before importing the UI
- `requirements.txt` — dependencies for the current Streamlit starter
- `integrations/tracing.py` — session-aware tracing, masking, and optional client setup
- `storage/response_cache.py` — exact cache keys, persistent responses, expiry and clearing
- `integrations/agent_bridge.py` — latest P4 runner adapter, response normalization and usage collection
- `integrations/external_p2.py` — isolated imports of the received flat P2 source
- `integrations/api_connection.py` — common API configuration and OpenAI-compatible transport
- `Dockerfile` — Python 3.11 image with a non-root user and health check
- `docker-compose.yml` — app service available locally on port 8501
- `../.dockerignore` — excludes credentials and generated data from the build context

## Next integration steps

Supply the full P3 parsed corpus and choose a configured Ollama or institute API
target. Docker mounts the P3 index and parsed corpus read-only; configure certificate
paths inside the container and use `host.docker.internal` for Ollama on a Mac host.
Then verify real research answers before running the approved gold evaluation set.

## Named user sessions

The app asks for a name before opening the chat. Each submission creates a unique
session, even when two people enter the same name. Conversations are assigned to
that session and the sidebar lists only its conversations. Existing conversations
without a session remain in the database and are not assigned to a new user.

The sidebar shows total tokens across the session's saved
assistant turns; each reply also shows its own usage. Response-cache and model-cache
hits add zero new tokens. These are provider-reported token counts; missing provider
usage is not an estimated billing amount.

Session records and usage are stored in the configured SQLite history database.
The session and selected chat IDs are preserved in URL query parameters, so refreshing
the same URL restores the name, active conversation, mode, and token totals. Opening
the bare app URL restores the last session remembered in this browser. Only session
and chat identifiers are saved in local storage; messages remain in SQLite. An explicit
session URL takes priority. Clearing browser site data removes this remembered link. Treat the session URL as a private resume link;
a name is a display label, not authenticated identity.

## Optional reranker

Set `RAG_RERANKER_ENABLED=false` in `p5-deployment/.env` to skip the local
BGE reranker and its download. Retrieval still combines BM25 and dense search,
returning passages in reciprocal-rank fusion order. Set it to `true` and install `requirements-local-models.txt`
to enable reranking. The lightweight environment template defaults to `false`. Restart Streamlit after changing this setting; an already
running download is not cancelled by editing the file. Cache keys distinguish
the two modes. Disabling reranking may affect passage relevance.

### P5 code organization

P5 follows a layered architecture with a Repository pattern for SQLite persistence
and an application service for chat turns. Dependencies flow from UI to service
and repository modules; backend and persistence code do not import Streamlit.

- `ui/chat.py`: chat page and input flow.
- `ui/sidebar.py`: conversation history and mode controls.
- `ui/messages.py`: message, token usage, citation, and evidence rendering.
- `ui/session.py`: session onboarding and conversation selection callbacks.
- `ui/browser_session.py`: browser resume storage component.
- `ui/styles.py`: existing presentation styles.
- `chat/chat_service.py`: turn orchestration, response caching, tracing, and history.
- `chat/response_backend.py`: dispatch to direct chat, research, or preview adapters.
- `chat/chat_models.py`: shared response data model.
- `storage/history_repository.py`: conversation, message, and session queries, including
  the shared ownership guard used by the service and UI callbacks.
- `storage/database.py`: SQLite connections and legacy schema migrations.
- `chat/chat_settings.py`: environment configuration and validation.
- `chat/rate_limit.py`: reusable sliding-window rate limit helper.

Existing adapter, API, streaming, cache, Redis, and tracing modules retain their
focused responsibilities. `app.py` re-exports the previous public chat/history
functions for callers; new code should import from the responsible module.
Tests patch dependencies in their owning module, such as `chat.chat_service`.
The Docker build includes the `app.py` entry point and the `chat`, `integrations`, `storage`, and `ui` packages.
