from typing import Any, TypedDict

class AgentState(TypedDict, total=False):
    user_query: str
    conversation_id: str
    history: list[dict[str, str]]
    context: dict[str, Any]          # carried companies, metric, fiscal period, basis
    gatekeeper: dict[str, Any]
    plan: dict[str, Any]
    subtasks: list[dict[str, Any]]
    current_subtask: int
    research: list[dict[str, Any]]
    observations: list[dict[str, Any]]
    analysis: list[dict[str, Any]]
    draft: dict[str, Any]
    critic: dict[str, Any]
    final: dict[str, Any]
    errors: list[str]
    step_count: int
    repair_count: int
    token_budget: int
    tokens_used: int
    approved: bool
    export_path: str
    trace_context: dict[str, Any]
