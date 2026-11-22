"""Limits and settings shared by every agent (P2). Change values here, not in code.

API facts (institute learner guide): 8,192 tokens input + output per call,
output 512 by default and 1,024 max, 1 active request per group key,
retry 429/503 after 2, 4 and 8 s.
"""

PROMPT_VERSION = "agents-v4"          # tag every trace with this (P5)

# ---- API limits ----------------------------------------------------------
CONTEXT_LIMIT = 8192                  # tokens, input + output
MAX_OUTPUT_TOKENS = 1024              # hard cap per call

# ---- Client behaviour (implemented in llm_client.py) ----------------------
REQUEST_TIMEOUT_S = 120               # read timeout per call
CONNECT_TIMEOUT_S = 15
RETRY_DELAYS_S = (2, 4, 8)            # on 429, 503, timeouts, connection errors -> 4 attempts max
RETRYABLE_STATUS = (429, 503)

# ---- JSON validation ------------------------------------------------------
MAX_JSON_REPAIRS = 2                  # LLM repair calls after the first invalid reply

# ---- Agent loop guards (enforced by P4's graph) ---------------------------
MAX_STEPS_PER_SUBTASK = 10
MAX_CRITIC_ROUNDS = 2                 # revision rounds before "could not verify"
MAX_SUBTASKS = 8                      # Planner output is cut to this

# ---- Per-agent output budgets (max_tokens) and temperature ----------------
AGENT_SETTINGS = {
    #  agent           max_tokens  temperature
    "gatekeeper":     {"max_tokens": 300, "temperature": 0.0},
    "planner":        {"max_tokens": 600, "temperature": 0.0},
    "query_writer":   {"max_tokens": 200, "temperature": 0.0},
    "analyst":        {"max_tokens": 700, "temperature": 0.0},
    "writer":         {"max_tokens": 700, "temperature": 0.0},
    "section_writer": {"max_tokens": 900, "temperature": 0.0},
    "critic":         {"max_tokens": 600, "temperature": 0.0},
    "repair":         {"max_tokens": 900, "temperature": 0.0},
}

# ---- Evidence budget (keeps every call inside 8,192 tokens) ---------------
MAX_EVIDENCE_CHUNKS = 5               # after P3's reranker
MAX_EVIDENCE_CHARS = 14000            # ~4k tokens; chunks beyond this are cut
MAX_CHUNK_CHARS = 2400                # ~512 tokens per chunk

# ---- Scope (replace with P1/P3's final list) ------------------------------
COVERED_COMPANIES = ["HUL", "ITC", "Nestle India", "Dabur", "Britannia", "Marico",
                     "Godrej Consumer", "Colgate-Palmolive India", "Tata Consumer", "Emami"]
COVERED_YEARS = ["FY22", "FY23", "FY24", "FY25", "FY26"]
