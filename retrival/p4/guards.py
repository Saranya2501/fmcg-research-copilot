import re
from p4.config import (
    PROHIBITED_PATTERNS, MAX_STEPS_PER_SUBTASK, MAX_REPAIR_ROUNDS,
    UNLISTED_OR_UNSUPPORTED,
)

UNSUPPORTED_COMPANY_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(name) for name in sorted(UNLISTED_OR_UNSUPPORTED)) + r")\b"
)

REFUSAL_MESSAGES = {
    "prohibited_investment_advice": "I can’t advise whether to buy, sell or hold a security. I can summarize historical reported performance with citations.",
    "prohibited_forecast": "I can’t forecast future results. I can compare historical reported results for the periods you choose.",
    "prohibited_valuation": "I can’t estimate fair value or a target price. I can retrieve historical financial metrics from company documents.",
    "unsupported_unlisted_company": "This copilot is scoped to the team-approved listed FMCG/CPG companies, so I can’t provide company-specific analysis for this company."
}

def gatekeeper(query: str, company_names: list[str] | None = None) -> dict:
    q = (query or "").lower()
    for code, phrases in PROHIBITED_PATTERNS.items():
        if any(phrase in q for phrase in phrases):
            return {"status": "refused", "refusal_code": code, "message": REFUSAL_MESSAGES[code]}
    if UNSUPPORTED_COMPANY_PATTERN.search(q):
        code = "unsupported_unlisted_company"
        return {"status": "refused", "refusal_code": code, "message": REFUSAL_MESSAGES[code]}
    return {"status": "allowed", "message": "Request passed the initial policy gate; company scope and evidence still require validation."}

def enforce_step_limit(step_count: int):
    if step_count > MAX_STEPS_PER_SUBTASK:
        raise RuntimeError("Subtask exceeded the 10-step limit")

def enforce_repair_limit(repair_count: int):
    if repair_count > MAX_REPAIR_ROUNDS:
        raise RuntimeError("Critic repair limit exceeded")

def detect_repeated_call(call_history: list[tuple]) -> bool:
    return len(call_history) != len(set(call_history))

def enforce_token_budget(used_tokens: int, budget: int):
    if used_tokens > budget:
        raise RuntimeError("Agent token budget exceeded")
