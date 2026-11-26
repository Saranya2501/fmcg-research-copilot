# P2 — Prompting & API Client

Owner: Himanshu

Owns the shared Qwen3-8B API client (with request queue, caching, retries, token logging), all agent prompt templates, and JSON reliability strategies.

## Implementation location

The P2 implementation used by the application is included in
[p4-agent/integration/p2_agents](../p4-agent/integration/p2_agents/):

- `llm_client.py` — shared LLM client, request serialization, retries, caching, and token logging.
- `agents.py` — agent entry points.
- `prompts/` — agent prompt templates.
- `config.py` — agent generation settings.
- `json_utils.py` and `schemas.py` — JSON repair and validation contracts.
- `tests/test_agents.py` — offline agent validation checks.

For the full Streamlit app, configure `p5-deployment/.env` using the
[P5 IITK setup instructions](../p5-deployment/README.md#iitk-institute-api).
P5 loads the bundled P2 modules through an isolated import adapter.

Run the offline checks from the repository root after installing the application dependencies:

```bash
.venv/bin/python p4-agent/integration/p2_agents/tests/test_agents.py
```
