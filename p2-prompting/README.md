# P2 — Prompting & API Client

Owner: Himanshu

Owns the shared Qwen3-8B API client (with request queue, caching, retries, token logging), all agent prompt templates, and JSON reliability strategies.

## Expected contents

- `client.py` — shared API client (all LLM calls go through this)
- `prompts/` — system and tool-call prompt templates per UC
- `config.py` — token limits, timeout, retry configuration
