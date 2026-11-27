"""P4 LangGraph orchestration. P2 model/prompt functions and P3 retrieval are injected."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Callable
from langgraph.graph import StateGraph, END
from p4.state import AgentState
from p4.config import MAX_STEPS_PER_SUBTASK, MAX_REPAIR_ROUNDS, TOOL_TIMEOUT_SECONDS, DEFAULT_TOKEN_BUDGET
from p4.guards import gatekeeper, enforce_step_limit, enforce_repair_limit, enforce_token_budget
from p4.schemas.models import CopilotResponse, Plan

def _invoke_with_timeout(fn, kwargs, timeout):
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(fn, **kwargs)
        try:
            return future.result(timeout=timeout)
        except FutureTimeout:
            future.cancel()
            raise TimeoutError("Tool execution timed out")

def build_graph(tool_registry: dict, planner_fn: Callable, researcher_fn: Callable,
                analyst_fn: Callable, writer_fn: Callable, critic_fn: Callable,
                repair_fn: Callable | None = None):
    """Build the Gatekeeper → Planner → Researcher → Analyst → Writer → Critic graph.

    Planner output may contain `subtasks`; otherwise `steps` are wrapped into one
    subtask for backward compatibility with the original P4 starter.
    """

    def gate_node(state: AgentState):
        result = gatekeeper(state.get("user_query", ""))
        final = None
        if result["status"] == "refused":
            final = CopilotResponse(status="refused", answer=result["message"],
                                     results=[], limitations=[],
                                     refusal_code=result["refusal_code"]).model_dump()
        return {"gatekeeper": result, "final": final}

    def route_after_gate(state):
        return "finish" if state.get("gatekeeper", {}).get("status") == "refused" else "plan"

    def plan_node(state: AgentState):
        raw = planner_fn(state["user_query"], state.get("context", {}))
        plan = Plan.model_validate(raw)
        subtasks = [x.model_dump() for x in plan.subtasks]
        if not subtasks:
            # Keep the original P4 planner's `steps` contract working.
            subtasks = [{
                "task_id": "SUBTASK-1", "objective": state["user_query"],
                "company": None, "metric": None, "period": None, "basis": None,
                "retrieval_query": state["user_query"],
                "tool_steps": [x.model_dump() for x in plan.steps]
            }]
        if len(subtasks) > MAX_STEPS_PER_SUBTASK:
            raise RuntimeError("Planner returned more than 10 subtasks")
        return {"plan": plan.model_dump(), "subtasks": subtasks, "current_subtask": 0,
                "research": [], "observations": [], "analysis": [], "step_count": 0,
                "repair_count": 0, "tokens_used": 0,
                "token_budget": state.get("token_budget", DEFAULT_TOKEN_BUDGET),
                "errors": []}

    def researcher_node(state: AgentState):
        gathered, observations = [], list(state.get("observations", []))
        count = 0
        for subtask in state.get("subtasks", []):
            q = subtask.get("retrieval_query") or subtask.get("objective") or state["user_query"]
            filters = {k: subtask.get(k) for k in ("company", "period", "basis") if subtask.get(k)}
            retrieval_steps = [
                step for step in subtask.get("tool_steps", [])
                if step.get("tool") in ("search_reports", "get_table")
            ]
            # Use an explicit planned search when present; otherwise perform the
            # default query rewrite/retrieval call. This avoids duplicate searches.
            if not any(step.get("tool") == "search_reports" for step in retrieval_steps):
                retrieval_steps.insert(0, {
                    "task_id": subtask.get("task_id"),
                    "tool": "search_reports",
                    "arguments": {"query": q, "k": 5, "filters": filters}
                })
            for step in retrieval_steps:
                name, args = step.get("tool"), dict(step.get("arguments", {}))
                if name not in tool_registry:
                    observations.append({"tool": name, "status": "tool_not_allowed"})
                    continue
                if name == "search_reports":
                    args.setdefault("query", q)
                    args.setdefault("k", 5)
                    args.setdefault("filters", filters)
                count += 1
                enforce_step_limit(count)
                try:
                    result = _invoke_with_timeout(tool_registry[name], args, TOOL_TIMEOUT_SECONDS)
                except Exception as exc:
                    result = {"status": "tool_error", "error_type": type(exc).__name__}
                gathered.append({"task_id": step.get("task_id"), "evidence": result})
                observations.append({"tool": name, "result": result})
        return {"research": gathered, "observations": observations, "step_count": count}

    def analyst_node(state: AgentState):
        result = analyst_fn(state["user_query"], state.get("research", []),
                            state.get("context", {}))
        return {"analysis": result if isinstance(result, list) else [result]}

    def executor_node(state: AgentState):
        observations = list(state.get("observations", []))
        calls, count = set(), state.get("step_count", 0)
        for subtask in state.get("subtasks", []):
            for step in subtask.get("tool_steps", []):
                name, args = step.get("tool"), step.get("arguments", {})
                if name in ("search_reports", "get_table"):
                    continue
                signature = (name, repr(sorted(args.items())))
                if signature in calls:
                    observations.append({"tool": name, "status": "repeated_call_blocked"})
                    continue
                calls.add(signature)
                if name not in tool_registry:
                    observations.append({"tool": name, "status": "tool_not_allowed"})
                    continue
                if name == "generate_report" and not state.get("approved", False):
                    observations.append({"tool": name, "result": {"status": "approval_required"}})
                    continue
                count += 1
                enforce_step_limit(count)
                try:
                    result = _invoke_with_timeout(tool_registry[name], args, TOOL_TIMEOUT_SECONDS)
                except Exception as exc:
                    result = {"status": "tool_error", "error_type": type(exc).__name__}
                observations.append({"task_id": step.get("task_id"), "tool": name, "result": result})
        return {"observations": observations, "step_count": count}

    def writer_node(state: AgentState):
        result = writer_fn(state["user_query"], state.get("analysis", []),
                           state.get("context", {}), state.get("history", []))
        if isinstance(result, dict) and "_usage" in result:
            usage = result.get("_usage") or {}
            used = state.get("tokens_used", 0) + int(usage.get("total_tokens", 0))
            enforce_token_budget(used, state.get("token_budget", DEFAULT_TOKEN_BUDGET))
            return {"draft": result.get("response", result), "tokens_used": used}
        return {"draft": result}

    def critic_node(state: AgentState):
        critique = critic_fn(state.get("draft", {}), state.get("observations", []))
        response = critique.get("response", state.get("draft", {}))
        try:
            validated = CopilotResponse.model_validate(response).model_dump()
            return {"critic": critique, "final": validated}
        except Exception:
            return {"critic": {"valid": False,
                               "feedback": critique.get("feedback", "Return the required P1 response schema.")},
                    "repair_count": state.get("repair_count", 0)}

    def route_after_critic(state):
        if state.get("final") is not None:
            return "finish"
        if repair_fn is None or state.get("repair_count", 0) >= MAX_REPAIR_ROUNDS:
            return "fallback"
        return "repair"

    def repair_node(state: AgentState):
        count = state.get("repair_count", 0) + 1
        enforce_repair_limit(count)
        revised = repair_fn(state.get("draft", {}), state.get("critic", {}),
                            state.get("observations", []))
        return {"draft": revised, "repair_count": count}

    def fallback_node(state: AgentState):
        fallback = CopilotResponse(
            status="partial",
            answer="I could not validate the response against the required response schema.",
            results=[],
            limitations=["The response did not pass validation after the permitted repair attempts."]
        )
        return {"final": fallback.model_dump()}

    graph = StateGraph(AgentState)
    for name, fn in [
        ("gatekeeper", gate_node), ("planner", plan_node), ("researcher", researcher_node),
        ("executor", executor_node), ("analyst", analyst_node), ("writer", writer_node),
        ("critic", critic_node), ("repair", repair_node), ("fallback", fallback_node)
    ]:
        graph.add_node(name, fn)
    graph.set_entry_point("gatekeeper")
    graph.add_conditional_edges("gatekeeper", route_after_gate, {"finish": END, "plan": "planner"})
    graph.add_edge("planner", "researcher")
    graph.add_edge("researcher", "executor")
    graph.add_edge("executor", "analyst")
    graph.add_edge("analyst", "writer")
    graph.add_edge("writer", "critic")
    graph.add_conditional_edges("critic", route_after_critic,
                                {"finish": END, "repair": "repair", "fallback": "fallback"})
    graph.add_edge("repair", "critic")
    graph.add_edge("fallback", END)
    return graph.compile()
