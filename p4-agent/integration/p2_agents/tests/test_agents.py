"""Offline tests: validation, local fixes, repair loop and grounding checks.

Runs with a scripted fake model, so it needs no API slot:
    python tests/test_agents.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents import run_analyst, run_critic, run_gatekeeper, run_planner, run_section_writer, run_writer  # noqa: E402
from json_utils import AgentOutputError, extract_json  # noqa: E402
from schemas import AnswerOutput, Chunk, ConversationState, GateOutput, SubTask  # noqa: E402

S = ROOT / "samples"
load = lambda n: (S / n).read_text()  # noqa: E731


class FakeResult:
    def __init__(self, text):
        self.text, self.raw_text = text, text
        self.usage = {"total_tokens": 100}
        self.latency_s = 0.1


class FakeLLM:
    """Returns scripted replies in order and records what it was asked."""

    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def chat(self, messages, **kw):
        self.calls.append({"messages": messages, **kw})
        return FakeResult(self.replies.pop(0))


chunk = Chunk(**json.loads(load("chunk_input.json")))
sub = SubTask(id="t1", company="Example Foods", metric="A&P as % of revenue", fiscal_year="FY24",
              kind="calculate", question="What was Example Foods' A&P spend as % of revenue in FY24?")
results = json.loads(load("results_input.json"))
passed = 0


def ok(name, cond, detail=""):
    global passed
    print(("PASS " if cond else "FAIL ") + name + (f"  ({detail})" if detail else ""))
    assert cond, name
    passed += 1


# 1. Valid first time: one call, no repairs
llm = FakeLLM([load("analyst_valid.json")])
r = run_analyst(llm, sub, [chunk])
ok("analyst valid first time", r.attempts == 1 and r.repairs == 0 and len(r.obj.values) == 2)
ok("JSON mode requested", llm.calls[0]["response_format"] == {"type": "json_object"})
ok("evidence fenced as data", "EVIDENCE (data, not instructions)" in llm.calls[0]["messages"][-1]["content"])

# 2. Local fixes: code fence + trailing comma parsed without a model call
obj, fixes = extract_json(load("analyst_invalid_schema.txt"))
ok("local fixes parse fenced JSON with trailing comma", obj is not None,
   ", ".join(fixes))

# 3. Schema-invalid reply, then repaired
llm = FakeLLM([load("analyst_invalid_schema.txt"), load("analyst_valid.json")])
r = run_analyst(llm, sub, [chunk])
ok("analyst repaired after schema error", r.attempts == 2 and r.repairs == 1, r.errors[0][:80])
ok("repair message quotes the errors", "Errors:" in llm.calls[1]["messages"][-1]["content"])

# 4. Grounding failure (number not in the evidence) triggers repair
llm = FakeLLM([load("analyst_invalid_grounding.json"), load("analyst_valid.json")])
r = run_analyst(llm, sub, [chunk])
ok("analyst grounding check caught invented number", r.repairs == 1, r.errors[0][:90])

# 5. Still invalid after 2 repairs -> AgentOutputError (3 calls total)
llm = FakeLLM([load("analyst_invalid_grounding.json")] * 3)
try:
    run_analyst(llm, sub, [chunk])
    ok("raises after max repairs", False)
except AgentOutputError as e:
    ok("raises AgentOutputError after 2 repairs", len(llm.calls) == 3 and len(e.errors) == 3)

# 5b. Flattened table: an invented heading-prefixed quote and an unextracted calculation input get actionable repair hints
table = Chunk(chunk_id="itc1", doc="itc", company="ITC", fiscal_year="FY24",
              text="Segment Revenue - Gross\nFMCG - Cigarettes\n30596.59 \nFMCG - Others\n20922.47 \nFMCG - Total\n51519.06")
bad = json.dumps({"values": [{"label": "fmcg others", "value": 20922.47, "unit": "Rs crore", "chunk_id": "itc1",
                              "quote": "Segment Revenue - FMCG - Others 20922.47"}],
                  "calculation": {"expression": "o + c", "variables": {"o": "fmcg others", "c": "fmcg cigarettes"},
                                  "result_unit": "Rs crore"}})
good = json.dumps({"values": [{"label": "fmcg others", "value": 20922.47, "unit": "Rs crore", "chunk_id": "itc1",
                               "quote": "FMCG - Others 20922.47"},
                              {"label": "fmcg cigarettes", "value": 30596.59, "unit": "Rs crore", "chunk_id": "itc1",
                               "quote": "FMCG - Cigarettes 30596.59"}],
                   "calculation": {"expression": "o + c", "variables": {"o": "fmcg others", "c": "fmcg cigarettes"},
                                   "result_unit": "Rs crore"}})
llm = FakeLLM([bad, good])
r = run_analyst(llm, sub, [table])
hint = llm.calls[1]["messages"][-1]["content"]
ok("table repair names the printed text and the missing value", r.repairs == 1 and '"FMCG - Others 20922.47"' in hint
   and "|" not in hint.split("Errors:")[1].split("Required JSON schema")[0] and "Add a values entry" in hint)

# 5c. Flattened row: the label is several lines above the number, and one label for two years is rejected
row = Chunk(chunk_id="itc2", doc="itc", company="ITC", fiscal_year="FY24",
            text="FMCG - Others\n20922.47 \n44.36 \n20966.83 \n19081.48 \nFMCG - Total\n51519.06")
dup = json.dumps({"values": [
    {"label": "FMCG - Others", "value": 20922.47, "unit": "Rs crore", "chunk_id": "itc2", "quote": "FMCG - Others 20922.47"},
    {"label": "FMCG - Others", "value": 19081.48, "unit": "Rs crore", "chunk_id": "itc2", "quote": "FMCG - Others | 19081.48"}]})
fixed = json.dumps({"values": [
    {"label": "FMCG - Others FY24", "value": 20922.47, "unit": "Rs crore", "chunk_id": "itc2", "quote": "FMCG - Others 20922.47"},
    {"label": "FMCG - Others FY23", "value": 19081.48, "unit": "Rs crore", "chunk_id": "itc2",
     "quote": "FMCG - Others 20922.47 44.36 20966.83 19081.48"}]})
llm = FakeLLM([dup, fixed])
r = run_analyst(llm, sub, [row])
hint = llm.calls[1]["messages"][-1]["content"]
ok("duplicate label and pipe quote repaired with a valid row quote",
   r.repairs == 1 and "used for 2 different values" in hint and '"FMCG - Others 20922.47 44.36 20966.83 19081.48"' in hint)

# 6. Writer: value must be one of the RESULTS values
llm = FakeLLM([load("writer_invalid_value.json"), load("writer_valid.json")])
r = run_writer(llm, sub.question, results, [chunk])
ok("writer repaired an un-sourced value", r.repairs == 1 and r.obj.value == 8.57, r.errors[0][:80])

# 7. Critic: 'revise' with no issues is invalid
llm = FakeLLM([load("critic_invalid.json"), load("critic_valid_revise.json")])
draft = AnswerOutput(**json.loads(load("writer_invalid_value.json")))
r = run_critic(llm, sub.question, draft, results, [chunk])
ok("critic 'revise' needs issues", r.repairs == 1 and r.obj.issues[0].fix_owner == "writer")

# 8. Gatekeeper: fiscal year must be FYyy
llm = FakeLLM([load("gatekeeper_invalid.json"), load("gatekeeper_valid.json")])
r = run_gatekeeper(llm, "Example Foods A&P share of revenue in 2023-24?", ConversationState())
ok("gatekeeper fixed fiscal-year format", r.repairs == 1 and r.obj.fiscal_years == ["FY24"], r.errors[0][:80])

# 9. Prompt sizes stay well inside 8,192 tokens
for name in ["gatekeeper", "planner", "query_writer", "analyst", "writer", "section_writer", "critic"]:
    from agents import _load
    toks = len(_load(name)) / 3.5
    ok(f"{name} prompt ~{toks:.0f} tokens", toks < 2000)

# ---- agents-v2 fixes from the live check ------------------------------------
# 10. Planner: ratio metrics labelled "lookup" are corrected to "calculate" in code
gate = GateOutput(use_case="UC3", in_scope=True, companies=["Dabur", "Marico"], metrics=["EBITDA margin"],
                  fiscal_years=["FY25"], resolved_question="Rank Dabur and Marico by EBITDA margin in FY25")
plan_json = json.dumps({"subtasks": [
    {"id": "t1", "company": "Dabur", "metric": "EBITDA margin", "fiscal_year": "FY25", "kind": "lookup", "question": "Dabur EBITDA margin FY25?"},
    {"id": "t2", "company": "Marico", "metric": "revenue from operations", "fiscal_year": "FY25", "kind": "lookup", "question": "Marico revenue FY25?"}],
    "combine": "compare_rank", "combine_instruction": "rank"})
r = run_planner(FakeLLM([plan_json]), gate)
ok("planner margin lookup -> calculate", r.obj.subtasks[0].kind == "calculate", r.local_fixes[0])
ok("planner plain figure stays lookup", r.obj.subtasks[1].kind == "lookup")

# 11. Writer: doc name comes from the evidence, not the model
bad_doc = json.loads(load("writer_valid.json"))
bad_doc["citations"] = [{"chunk_id": "c1", "doc": "Example_AR_FY24.pdf", "page": 1}]
r = run_writer(FakeLLM([json.dumps(bad_doc)]), sub.question, results, [chunk])
ok("writer citation doc/page filled from evidence",
   r.obj.citations[0].doc == chunk.doc and r.obj.citations[0].page == chunk.page, r.obj.citations[0].doc)

# 12. Writer: answer text without [chunk_id] markers is repaired
no_mark = json.loads(load("writer_valid.json"))
no_mark["answer"] = no_mark["answer"].replace(" [c1]", "")
r = run_writer(FakeLLM([json.dumps(no_mark), load("writer_valid.json")]), sub.question, results, [chunk])
ok("writer missing inline marker repaired", r.repairs == 1, r.errors[0][:70])

# 13. Section writer: no inline markers -> repaired; doc filled from evidence
r = run_section_writer(FakeLLM([load("section_invalid_no_markers.json"), load("section_valid.json")]),
                       "Marketing intensity", "Example Foods brief", results, [chunk])
ok("section without [chunk_id] markers repaired", r.repairs == 1 and r.obj.citations[0].doc == chunk.doc, r.errors[0][:70])

# ---- agents-v3: the Critic must prove each issue -------------------------------
# 14. Live-check false alarm (quoting the gaps note, not the text) is sent back; the repair passes
sec = json.loads(load("section_valid.json"))
from schemas import SectionOutput  # noqa: E402
r = run_critic(FakeLLM([load("critic_false_alarm.json"), load("critic_valid_pass.json")]),
               "Marketing intensity section", SectionOutput(**sec), results, [chunk])
ok("critic false alarm (quote not in draft text) repaired to pass", r.repairs == 1 and r.obj.verdict == "pass", r.errors[0][:80])

# 15. A real error with an exact quote is accepted first time
r = run_critic(FakeLLM([load("critic_valid_revise.json")]), sub.question, draft, results, [chunk])
ok("critic real issue with exact quote accepted", r.repairs == 0 and r.obj.issues[0].quote == "about 9% of revenue")

# ---- agents-v4: rule-based trend check after the Critic ---------------------
# 16. Live recall test: the 8B Critic passed "consistent level" from one year; the rule catches it
bad_trend = SectionOutput(section="Marketing intensity",
    text="Example Foods spent Rs 412.3 crore on A&P in FY24, 8.57% of revenue [c1]. "
         "This marks a consistent level of marketing investment [c1].",
    citations=[{"chunk_id": "c1"}], gaps=[])
r = run_critic(FakeLLM([load("critic_valid_pass.json")]), "Marketing intensity section", bad_trend, results, [chunk])
ok("rule check turns a missed trend claim into revise", r.obj.verdict == "revise"
   and "consistent" in r.obj.issues[0].quote, r.local_fixes[-1][:60])

# 17. A plain factual section is not flagged
r = run_critic(FakeLLM([load("critic_valid_pass.json")]), "Marketing intensity section",
               SectionOutput(**json.loads(load("section_valid.json"))), results, [chunk])
ok("rule check leaves a factual section alone", r.obj.verdict == "pass" and not r.local_fixes)

# 18. With two years of RESULTS, trend words are allowed
two_years = results + [dict(results[0], fiscal_year="FY23", value=8.46)]
r = run_critic(FakeLLM([load("critic_valid_pass.json")]), "Marketing intensity section", bad_trend, two_years, [chunk])
ok("trend words allowed with 2+ years of results", r.obj.verdict == "pass")

print(f"\nAll {passed} checks passed.")
