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

# ---- agents-v5: grounding works on real table layouts ---------------------
sub_pct = sub
sub = SubTask(id="t1", company="Example Foods", metric="profit after tax", fiscal_year="FY23",
              kind="lookup", question="What was Example Foods' profit after tax in FY23?")
table_chunk = Chunk(chunk_id="t1", company="Example Foods", doc="ExampleFoods_AR_FY24.pdf", page=45,
                    text="10-year financial highlights (Rs million)\nProfit after Tax\n31,089\n23,905\n21,184")
table_ok = json.dumps({"values": [{"label": "profit after tax", "value": 23905, "unit": "Rs million",
                       "fiscal_year": "FY23", "chunk_id": "t1", "quote": "Profit after Tax 23,905"}],
                       "calculation": None, "missing": []})
r = run_analyst(FakeLLM([table_ok]), sub, [table_chunk])
ok("table row label + number accepted without exact quote", r.repairs == 0 and r.obj.values[0].unit == "Rs million")
table_bad = table_ok.replace("23905", "23950").replace("23,905", "23,950")
r = run_analyst(FakeLLM([table_bad, table_ok]), sub, [table_chunk])
ok("number not in the table still rejected", r.repairs == 1, r.errors[0][:70])

# ---- agents-v6: small talk never reaches the Planner ----------------------
from agents import quick_route  # noqa: E402
ok("quick_route answers greetings with no model call",
   all(quick_route(m) for m in ["hi", "Hello!", "thanks", "what can you do?", "", "ok"]))
ok("quick_route passes real questions through",
   quick_route("hi, what was Dabur's revenue in FY24?") is None and quick_route("HUL margin FY25") is None)
uc0 = json.dumps({"use_case": "UC0", "in_scope": True, "companies": [], "metrics": [], "fiscal_years": [],
                  "resolved_question": "good evening team", "direct_reply": "Hello! Ask me about FMCG filings."})
g = run_gatekeeper(FakeLLM([uc0]), "good evening team", ConversationState()).obj
ok("gatekeeper UC0 carries a direct reply", g.use_case == "UC0" and g.direct_reply)
try:
    run_planner(FakeLLM([]), g); ok("planner refuses UC0", False)
except ValueError:
    ok("planner refuses to plan UC0/UC7", True)

# ---- agents-v7: long real chunk ids, empty calculations, unit labels ------
from agents import compute_result  # noqa: E402
from schemas import AnalystOutput  # noqa: E402
long_id = "hul_annual_report_fy24_hul_annual_report_2024_p0179_c906"
hul = Chunk(chunk_id=long_id, company="HUL", fiscal_year="FY24", doc="HUL_Annual_Report_2024.pdf", page=179,
            text="Consolidated Statement of Profit and Loss. Revenue from operations 61,896 60,580")
res = [{"subtask_id": "t1", "company": "HUL", "metric": "revenue", "fiscal_year": "FY24", "value": 61896.0,
        "unit": "Rs crore", "chunk_ids": [long_id]}]
short = json.dumps({"answer": "HUL's FY24 revenue from operations was Rs 61,896 crore [c906].", "value": 61896,
                    "unit": "Rs crore", "fiscal_year": "FY24", "citations": [{"chunk_id": "c906"}], "refused": False})
llm = FakeLLM([short])
r = run_writer(llm, "HUL revenue FY24?", res, [hul])
ok("model sees short id E1, not the long id", "[E1]" in llm.calls[0]["messages"][-1]["content"]
   and long_id not in llm.calls[0]["messages"][-1]["content"])
ok("shortened id [c906] accepted and mapped back to the real id",
   r.repairs == 0 and r.obj.citations[0].chunk_id == long_id and f"[{long_id}]" in r.obj.answer, r.obj.answer[-30:])

empty_calc = json.dumps({"values": [{"label": "revenue from operations", "value": 61896, "unit": "Rs crore",
                         "fiscal_year": "FY24", "chunk_id": "E1", "quote": "Revenue from operations 61,896"}],
                         "calculation": {"expression": "", "variables": {}, "result_unit": "Rs crore"}, "missing": []})
r = run_analyst(FakeLLM([empty_calc]), sub, [hul])
ok("empty calculation removed; value mapped to real chunk id",
   r.obj.calculation is None and r.obj.values[0].chunk_id == long_id)
ok("compute_result: plain lookup", compute_result(r.obj) == (61896.0, "Rs crore"))
mil = AnalystOutput(values=[{"label": "pat", "value": 23905, "unit": "Rs million", "chunk_id": "x", "quote": "23,905"}],
                    calculation={"expression": "pat", "variables": {"pat": "pat"}, "result_unit": "Rs million"})
ok("compute_result converts million and labels the result Rs crore", compute_result(mil) == (2390.5, "Rs crore"))

# ---- agents-v8: growth calculations on real pages --------------------------
from agents import _resolve  # noqa: E402
ok("lowercase 'e1' resolves", _resolve("e1", [Chunk(chunk_id="E1", company="x", doc="d", text="t")]) == "E1")
dup = json.dumps({"values": [
    {"label": "revenue from operations", "value": 61896, "unit": "Rs crore", "fiscal_year": "FY24", "chunk_id": "E1", "quote": "Revenue from operations 61,896"},
    {"label": "revenue from operations", "value": 60580, "unit": "Rs crore", "fiscal_year": "FY23", "chunk_id": "E1", "quote": "61,896 60,580"}],
    "calculation": {"expression": "(a - b) / b * 100", "variables": {"a": "revenue from operations", "b": "revenue from operations"}, "result_unit": "%"}, "missing": []})
fixed = dup.replace('"revenue from operations", "value": 61896', '"revenue from operations FY24", "value": 61896').replace(
    '"revenue from operations", "value": 60580', '"revenue from operations FY23", "value": 60580').replace(
    '"a": "revenue from operations", "b": "revenue from operations"', '"a": "revenue from operations FY24", "b": "revenue from operations FY23"')
r = run_analyst(FakeLLM([dup, fixed]), sub_pct, [hul])
ok("duplicate labels sent back; growth computed correctly", r.repairs == 1 and compute_result(r.obj) == (2.17, "%"), r.errors[0][:60])
no100 = fixed.replace(" * 100", "")
r = run_analyst(FakeLLM([no100, fixed]), sub_pct, [hul])
ok("percentage without * 100 sent back", r.repairs == 1, r.errors[0][:60])



# ---- agents-v10 -------------------------------------------------------------
from schemas import Calculation
ok("unknown result unit becomes None", Calculation(expression="a/b", variables={}, result_unit="per unit").result_unit is None)
pct_chunk = Chunk(chunk_id="p1", company="Example Foods", doc="ExampleFoods_AR_FY24.pdf", page=12,
                  text="Operating Profit (FY24) 3,240 Revenue from operations (FY24) 16,000")
loose = json.dumps({"values": [
    {"label": "Operating Profit (FY24)", "value": 3240, "unit": "Rs crore", "fiscal_year": "FY24", "chunk_id": "p1", "quote": "Operating Profit (FY24) 3,240"},
    {"label": "Revenue from operations (FY24)", "value": 16000, "unit": "Rs crore", "fiscal_year": "FY24", "chunk_id": "p1", "quote": "Revenue from operations (FY24) 16,000"}],
    "calculation": {"expression": "op / rev * 100", "variables": {"op": "operating profit FY24", "rev": "revenue from operations FY24"}, "result_unit": "percent of revenue"},
    "missing": []})
sub_m = SubTask(id="t1", company="Example Foods", metric="operating margin", fiscal_year="FY24", kind="calculate",
                question="What was Example Foods' operating profit margin in FY24?")
r = run_analyst(FakeLLM([loose]), sub_m, [pct_chunk])
ok("loose variable labels matched without a repair", r.repairs == 0, r.errors[:1])
ok("calculator gives 20.25 %", compute_result(r.obj) == (20.25, "%"), compute_result(r.obj))
money_only = json.dumps({"values": [loose and json.loads(loose)["values"][0]], "calculation": None, "missing": []})
r = run_analyst(FakeLLM([money_only, loose]), sub_m, [pct_chunk])
ok("margin question answered with a money figure is sent back", r.repairs == 1, r.errors[:1])

# ---- agents-v10.1: companies outside the covered list are refused in code -----
from schemas import ConversationState
gate_amul = json.dumps({"use_case": "UC3", "in_scope": True, "refusal_reason": None, "refusal_message": None,
                        "companies": ["Amul", "Patanjali", "HUL"], "metrics": ["profitability"], "fiscal_years": [],
                        "resolved_question": "Rank Amul, Patanjali and HUL by profitability."})
r = run_gatekeeper(FakeLLM([gate_amul]), "Rank Amul, Patanjali and HUL by profitability.", ConversationState())
ok("unlisted companies refused even when the model says in scope",
   not r.obj.in_scope and r.obj.use_case == "UC7" and r.obj.refusal_reason == "out_of_scope", r.obj.refusal_message)
gate_ok = gate_amul.replace('"Amul", "Patanjali", "HUL"', '"Nestl\u00e9 India", "Hindustan Unilever", "Godrej Consumer Products"')
r = run_gatekeeper(FakeLLM([gate_ok]), "Compare Nestle, HUL and GCPL", ConversationState())
ok("covered companies in any spelling stay in scope", r.obj.in_scope)
gate_generic = gate_amul.replace('"Amul", "Patanjali", "HUL"', '"listed FMCG companies"')
r = run_gatekeeper(FakeLLM([gate_generic]), "Which listed FMCG companies had the highest margin?", ConversationState())
ok("generic 'FMCG companies' is not treated as an unlisted company", r.obj.in_scope)

# ---- agents-v10.2: the Critic can no longer fail an answer --------------------
odd = json.dumps({"verdict": "revise", "issues": [{"claim": "x", "quote": "8.57%", "correct": "y",
                  "problem": "misleading_comparison", "fix_owner": "the writer", "instruction": "z"}]})
r = run_critic(FakeLLM([odd]), "Marketing intensity section", SectionOutput(**json.loads(load("section_valid.json"))), results, [chunk])
ok("invented problem label mapped, not rejected", r.repairs == 0 and r.obj.issues[0].problem == "unsupported"
   and r.obj.issues[0].fix_owner == "writer", r.obj.issues[0].problem)
bad_quote = odd.replace('"8.57%"', '"words that are not in the draft"')
r = run_critic(FakeLLM([bad_quote] * 3), "Marketing intensity section", SectionOutput(**json.loads(load("section_valid.json"))), results, [chunk])
ok("unusable Critic output keeps the draft, marked unverified", r.obj.verified is False and r.obj.verdict == "pass")

print(f"\nAll {passed} checks passed.")
