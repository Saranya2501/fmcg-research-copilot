"""One real call per agent on the sample chunk (run in a booked API slot, ~1 minute).

    python live_check.py

Prints each agent's validated output, attempts and repairs, so P4 can see real
Qwen3-8B behaviour before wiring the graph.
"""

import json

from agents import (run_analyst, run_critic, run_gatekeeper, run_planner, run_query_writer,
                    run_section_writer, run_writer)
from json_utils import AgentOutputError
from llm_client import LLMClient
from schemas import Chunk, ConversationState

llm = LLMClient()
chunk = Chunk(**json.load(open("samples/chunk_input.json")))
results = json.load(open("samples/results_input.json"))
summary = []


def show(name, fn):
    try:
        r = fn()
        print(f"\n== {name}: attempts {r.attempts}, repairs {r.repairs}, fixes {r.local_fixes}, "
              f"{r.tokens} tokens, {r.latency_s}s")
        print(r.obj.model_dump_json(indent=1)[:1200])
        summary.append((name, "ok", r.attempts, r.repairs))
        return r.obj
    except AgentOutputError as e:
        print(f"\n== {name}: FAILED after repairs: {e.errors}\n   last raw: {e.last_raw[:300]}")
        summary.append((name, "failed", 3, 2))
        return None


gate = show("gatekeeper", lambda: run_gatekeeper(
    llm, "What share of its FY24 revenue did Dabur spend on advertising?", ConversationState(), tag="live"))
show("gatekeeper (refusal)", lambda: run_gatekeeper(
    llm, "Should I buy Marico shares before results?", ConversationState(), tag="live"))
if gate:
    plan = show("planner", lambda: run_planner(llm, gate, tag="live"))
plan3 = None
gate3 = show("gatekeeper (comparison)", lambda: run_gatekeeper(
    llm, "Rank Dabur, Marico and Emami by EBITDA margin in FY25", ConversationState(), tag="live"))
if gate3:
    plan3 = show("planner (comparison)", lambda: run_planner(llm, gate3, tag="live"))

from schemas import SubTask  # noqa: E402
sub = SubTask(id="t1", company="Example Foods", metric="A&P as % of revenue", fiscal_year="FY24",
              kind="calculate", question="What was Example Foods' A&P spend as % of revenue in FY24?")
show("query_writer", lambda: run_query_writer(llm, sub, tag="live"))
show("analyst", lambda: run_analyst(llm, sub, [chunk], tag="live"))
draft = show("writer", lambda: run_writer(llm, sub.question, results, [chunk], tag="live"))
section = show("section_writer", lambda: run_section_writer(
    llm, "Marketing intensity", "Example Foods competitor brief", results, [chunk], tag="live"))
if section:
    show("critic (section)", lambda: run_critic(
        llm, "Marketing intensity section of an Example Foods brief", section, results, [chunk], tag="live"))
if draft:
    show("critic", lambda: run_critic(llm, sub.question, draft, results, [chunk], tag="live"))

# Critic recall: known-bad drafts must come back "revise"
from schemas import AnswerOutput, SectionOutput  # noqa: E402
bad_number = AnswerOutput(**json.load(open("samples/writer_invalid_value.json")))
bad_trend = SectionOutput(section="Marketing intensity",
    text="Example Foods spent Rs 412.3 crore on A&P in FY24, 8.57% of revenue [c1]. "
         "This marks a consistent level of marketing investment [c1].",
    citations=[{"chunk_id": "c1"}], gaps=[])
show("critic recall: wrong number", lambda: run_critic(llm, sub.question, bad_number, results, [chunk], tag="live"))
show("critic recall: trend claim", lambda: run_critic(
    llm, "Marketing intensity section of an Example Foods brief", bad_trend, results, [chunk], tag="live"))

print("\nSummary (agent, status, attempts, repairs):")
for row in summary:
    print("  ", row)
