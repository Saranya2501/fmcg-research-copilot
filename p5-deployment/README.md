# P5 — Observability & Deployment

Owner: Irfan

Owns Langfuse tracing integration, the evaluation runner with trace output, Streamlit entry point, and Docker configuration.

## Run with Docker

Install and start Docker Desktop, then run from the repository root:

```bash
docker compose -f p5-deployment/docker-compose.yml up --build -d
```

Open http://localhost:8501. The app runs in preview mode until P4's agent is connected.
It includes a chat input, conversation history for the current session, and a New chat
button. It accepts questions but does not generate research answers yet.

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
streamlit run p5-deployment/app.py
```

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
- `Dockerfile` — Python 3.11 image with a non-root user and health check
- `docker-compose.yml` — app service available locally on port 8501
- `../.dockerignore` — excludes credentials and generated data from the build context

## Next integration steps

Connect P4's agent to the chat input, then render its answer and citations.
Add P2/P4 dependencies and source files to the image when that interface is ready.
Retrieval will need the three P3 index files plus `parsed/all_chunks.jsonl`, supplied
as mounted data rather than baked into the image. Langfuse tracing and evaluation
with trace output remain to be implemented; this starter does not require API keys.
