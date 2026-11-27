# P2 → P4 interface: LLM client and agents (agents-v10.2)

Everything P4 needs to wire the agent graph. All examples use the fictional company Example Foods.

## 1. Files

| File | What it is |
| --- | --- |
| `llm_client.py` | Shared Qwen3-8B client: API or local Ollama, CA cert, one-at-a-time lock, retries, cache, call log |
| `config.py` | All limits: tokens, timeouts, retries, JSON repairs, loop guards, evidence budget, covered companies |
| `schemas.py` | Pydantic input/output models for every agent |
| `json_utils.py` | `call_json()`: JSON mode → local fixes → schema validation → grounding check → up to 2 repairs |
| `agents.py` | One function per agent (below) |
| `prompts/*.md` | Prompt files, versioned as `agents-v10.2`; `_shared.md` is prepended to each |
| `samples/` | Valid and invalid JSON examples |
| `tests/test_agents.py` | Offline tests with a fake model (`python tests/test_agents.py`) |
| `live_check.py` | One real call per agent; run in an API slot |

## 2. Shared LLM client (confirmed interface)

```python
from llm_client import LLMClient
llm = LLMClient()            # reads .env; LLM_TARGET=api or local
r = llm.chat(messages, tag="q017.t2.analyst", max_tokens=700, temperature=0.0,
             tools=None, tool_choice=None, response_format={"type": "json_object"},
             use_cache=None, sample_id=0)
r.text          # str, answer with any <think> removed
r.raw_text      # str, as returned
r.tool_calls    # [{"id", "name", "arguments"(JSON string)}]  native tool calls
r.usage         # {"prompt_tokens", "completion_tokens", "total_tokens"}
r.latency_s     # float
r.finish_reason # "stop" | "length" | "tool_calls"
r.cached        # bool
```

Agents use JSON mode, not tools. **P4 calls the tools** (calculator, unit_convert, search_reports, get_table, company_lookup, metric_lookup, generate_report) in code, using agent outputs as arguments. Native tool calling is available if P4 later wants the model to choose tools.

## 3. Limits and retries (`config.py`)

| Setting | Value |
| --- | --- |
| Context window | 8,192 tokens input + output (API limit) |
| Max output per call | 1,024 (API limit); per-agent `max_tokens`: gatekeeper 300, planner 600, query_writer 200, analyst 700, writer 700, section_writer 900, critic 600, repair 900 |
| Temperature | 0.0 for all agents |
| Timeouts | 120 s read, 15 s connect |
| Retries | 429, 503, timeouts, connection errors: wait 2, 4, 8 s, then fail (4 attempts) |
| Concurrency | 1 request at a time (thread + file lock); book API slots across the team |
| JSON repairs | Up to 2 repair calls per agent step (3 calls max), then `AgentOutputError` |
| Critic rounds | Up to 2 revision rounds, then mark "could not verify" |
| Steps | Up to 10 per sub-task; up to 8 sub-tasks per request |
| Evidence | Top 5 chunks, 2,400 characters each, 14,000 characters total |
| Thinking | Off (the server has it disabled anyway) |

## 4. Agent functions

Each returns a `JsonResult`: `.obj` (validated output), `.attempts`, `.repairs`, `.local_fixes`, `.errors`, `.tokens`, `.latency_s`. After 2 failed repairs, each raises `AgentOutputError(agent, errors, last_raw)`.

```python
run_gatekeeper(llm, user_message: str, state: ConversationState, tag="") -> JsonResult[GateOutput]
run_planner(llm, gate: GateOutput, tag="") -> JsonResult[PlanOutput]
run_query_writer(llm, subtask: SubTask, tag="") -> JsonResult[QueryOutput]
run_analyst(llm, subtask: SubTask, chunks: list[Chunk], tag="") -> JsonResult[AnalystOutput]
run_writer(llm, question: str, results: list[dict], chunks: list[Chunk], tag="") -> JsonResult[AnswerOutput]
run_section_writer(llm, section: str, request: str, results: list[dict], chunks: list[Chunk], tag="") -> JsonResult[SectionOutput]
run_critic(llm, question: str, draft: AnswerOutput | SectionOutput, results: list[dict], chunks: list[Chunk], tag="") -> JsonResult[CriticOutput]
```

Built-in checks beyond the schema (failures trigger a repair):
- **Analyst:** every value's quote must appear verbatim in its chunk and contain the number; calculation variables must match extracted labels.
- **Writer:** `value` must be one of the RESULTS values (±0.5%); every citation must be an evidence chunk; non-refusals must cite something; the answer text must carry `[chunk_id]` markers that match evidence chunks.
- **Section writer:** ≤ 300 words (330 hard stop); citations must be evidence chunks; the text must carry `[chunk_id]` markers.
- **Planner:** unique ids; UC5 must use `combine: "brief"`. Code then relabels any `lookup` whose metric is a margin, %, share, ratio or growth as `calculate` (no extra call; recorded in `.local_fixes`).
- **Citations:** the model gives only `chunk_id`; code fills `doc` and `page` from the evidence chunk, so file names can't be invented.

### Changes in agents-v2 (from the first live check)
| Live-check finding | Fix |
| --- | --- |
| Planner labelled "EBITDA margin" and "% of revenue" as `lookup` | Prompt rule + code relabels ratio metrics as `calculate` |
| Writer cited `Example_AR_FY24.pdf`, a name copied from its prompt example, not the evidence | Citations carry `chunk_id` only; code fills `doc`/`page` |
| Section writer claimed a "consistent" trend from one year of data | Prompt bans trend/judgement words without 2+ years of figures; Critic rule 6 flags them as `unsupported` |
| Section text had no `[chunk_id]` markers | Prompt requires them; code check sends it back for repair |

### Changes in agents-v3 (from the second live check)
| Live-check finding | Fix |
| --- | --- |
| Critic raised false alarms on a correct section: a "wrong_unit" for a unit that was already right, and "unsupported" on the gaps note | Critic must quote the exact wrong words and state the correct value; code rejects issues whose quote isn't in the draft text; prompt says missing-data notes are correct behaviour and adds a worked "pass" example |
| (still prompt-only) A false alarm that quotes real draft text, like the "wrong_unit" one | Can't be caught in code; P5 should track Critic false-alarm rate on the gold set |

### Changes in agents-v4 (Critic recall test)
| Finding | Fix |
| --- | --- |
| Critic caught a wrong number ("about 9%") but **passed** an unsupported trend claim ("consistent level" from one year) | Rule-based check runs after the LLM Critic, with no extra call: trend/judgement words (consistent, strong, improved, declined, robust, record…) are flagged when RESULTS hold fewer than 2 fiscal years for a company, unless the sentence is quoted from the evidence or says data is missing. Any rule issue sets the verdict to `revise` and is recorded in `.local_fixes` |
- **Gatekeeper:** fiscal years must be `FYyy`.
- **Critic:** `revise` must list at least one issue; every issue carries `quote` (exact wrong words) and `correct`, and code rejects quotes that are not in the draft's answer/text (repair).

## 5. How P4 chains them

```
gate = run_gatekeeper(...)        -> if not gate.in_scope: show gate.refusal_message, stop
plan = run_planner(gate)
for t in plan.subtasks:           (each ≤ 10 steps)
    q  = run_query_writer(t)      -> P4: chunks = retrieve(q.queries, filters=q.filters)  (P3)
    a  = run_analyst(t, chunks)   -> P4: unit_convert values to Rs crore if needed;
                                        calculator(a.calculation) -> value
    results.append({"subtask_id": t.id, "company": t.company, "metric": t.metric,
                    "fiscal_year": t.fiscal_year, "value": value, "unit": unit,
                    "chunk_ids": [...], "inputs": "412.3 / 4,812.6 Rs crore"})
combine:
    single_answer / compare_rank / summarise -> draft = run_writer(question, results, chunks)
    brief -> one run_section_writer per section; code assembles the brief
critic = run_critic(question, draft, results, chunks)
    revise -> route each issue to issue.fix_owner (researcher / analyst / writer), max 2 rounds
    pass   -> answer to user (or brief preview -> human approval -> generate_report)
```

For `compare_rank`, P4 should sort the results in code and pass the order to the Writer. The baseline showed the 8B model ranking by revenue instead of the metric asked.

## 6. Sample input and output

**Chunk (from P3's retrieve)** — `samples/chunk_input.json`
```json
{"chunk_id": "c1", "company": "Example Foods", "fiscal_year": "FY24", "doc_type": "annual_report",
 "doc": "ExampleFoods_AR_FY24.pdf", "page": 88, "section": "Statement of Profit and Loss",
 "text": "Consolidated Statement of Profit and Loss ... Revenue from operations 4,812.6; Advertisement and sales promotion 412.3; EBITDA 875.9."}
```

**Analyst output (valid)** — `samples/analyst_valid.json`
```json
{"values": [{"label": "advertisement and sales promotion", "value": 412.3, "unit": "Rs crore", "fiscal_year": "FY24", "chunk_id": "c1", "quote": "Advertisement and sales promotion 412.3"},
            {"label": "revenue from operations", "value": 4812.6, "unit": "Rs crore", "fiscal_year": "FY24", "chunk_id": "c1", "quote": "Revenue from operations 4,812.6"}],
 "calculation": {"expression": "a_p / revenue * 100", "variables": {"a_p": "advertisement and sales promotion", "revenue": "revenue from operations"}, "result_unit": "%"},
 "missing": []}
```

**Invalid examples and what happens**

| Sample | Problem | Handling |
| --- | --- | --- |
| `analyst_invalid_schema.txt` | Code fence, trailing comma, value as a string, unit "crores", missing fields | Fence and comma fixed locally; schema errors sent back; repaired in 1 call |
| `analyst_invalid_grounding.json` | Number 4,900.0 not in the evidence | Grounding check fails; repair asked; `AgentOutputError` if still wrong after 2 |
| `writer_invalid_value.json` | "about 9%" when RESULTS say 8.57 | Value check fails; repaired to 8.57 |
| `critic_invalid.json` | `revise` with no issues | Schema check fails; repaired |
| `gatekeeper_invalid.json` | Fiscal year "2023-24" | Format check fails; repaired to "FY24" |

## 7. Open points for P4
- Calculator input: evaluate `a.calculation.expression` with `variables` mapped to the extracted values. Allow only numbers, variables and `+ - * / ( )`.
- Convert `Rs lakh` / `Rs million` to `Rs crore` with unit_convert **before** the calculator when units differ.
- Log `JsonResult.attempts`, `.repairs` and `.errors` on every step: P5 needs them for the JSON validity metric.

### Changes in agents-v5 (real report pages)
| Finding | Fix |
| --- | --- |
| Scope is FY17–FY26 (last ten years) | `COVERED_YEARS` and the Gatekeeper/shared prompts updated |
| On real annual-report tables the Analyst's quote failed the exact-match check (row label and number are separated by other years' columns) | Grounding now requires the number to appear in the chunk and in the quote, and the quote's words to come from the chunk; an exact contiguous quote is no longer required. Invented numbers are still rejected |
| Reports print figures in Rs lakh or Rs million (Nestlé, Colgate) | Analyst reports the unit as printed; P4's `unit_convert` must convert lakh (÷100) and million (÷10) to crore before the calculator and Writer |

### Changes in agents-v6 (small talk and latency)
| Finding | Fix |
| --- | --- |
| "hi" went through the whole chain; the Planner turned a greeting into an invalid task and errored | **`quick_route(message)`**: call it first; greetings, thanks, "help", "what can you do?" get a canned reply with **no model call** |
| Small talk the regex doesn't catch | Gatekeeper has **UC0** (small talk / help) with `direct_reply`; show it and stop |
| Planner reached for non-research input | `run_planner` raises `ValueError` for UC0, UC7 or `in_scope=false`: show `direct_reply` or `refusal_message` instead |

Recommended flow: `quick_route` → (text? reply, stop) → `run_gatekeeper` → UC0: `direct_reply`, stop · UC7 / not in scope: `refusal_message`, stop · otherwise plan. Also wrap each agent step in `try/except AgentOutputError` and show a polite "couldn't complete that" message instead of a stack trace.

### Changes in agents-v7 (first run on real chunks)
| Finding (real-chunk test, 15 questions) | Fix |
| --- | --- |
| Writer shortened long chunk ids (`..._p0179_c906` → `c906`), so the citation check rejected the answer (2 errors) | Agents now see short ids **E1..E5**; any id the model writes (E1, the real id, or a shortened one) is resolved, and all output ids are mapped back to the real chunk ids. P4 passes real chunks in and gets real ids out; nothing to change |
| Analyst returned a calculation with an empty expression on plain lookups (2 errors) | Empty calculations are dropped (`local_fixes: "empty calculation removed"`) |
| A converted value kept the label "Rs million", so the Writer wrote "2,390.5 million" (Critic caught it) | **`compute_result(analyst_output)`** converts lakh/million to crore, runs the calculation safely, and always labels money results "Rs crore". **P4: use this instead of your own calculator + unit_convert** |
| Chunks carry `standalone_consolidated` from P3 | `Chunk.standalone_consolidated`; shown in the evidence header so the Analyst can prefer consolidated |

### Changes in agents-v8 (38-question real-chunk run: 19/38 correct)
| Finding | Fix |
| --- | --- |
| Growth questions gave 0.0, -99, 60,480 or 1,357%: the Analyst labelled FY24 and FY23 figures identically ("revenue from operations"), so the calculation used the same number twice | Labels must be unique (code check + repair); prompt asks for the fiscal year in each label and has a worked growth example |
| A margin came out as 0.16% instead of 16% | A `%` result without `* 100` is sent back for repair |
| Model wrote `e1` instead of `E1` (4 errors) | Chunk ids resolved case-insensitively |

### Changes in agents-v9 (38-question run: 24/38 correct)
| Finding | Fix |
| --- | --- |
| On plain lookups the Analyst sometimes added a calculation (EBITDA → margin), so the result disagreed with the question | Calculations are dropped when the sub-task is a `lookup` |
| Expression `"null"` crashed the calculator | Treated as no calculation |
| Units written loosely ("Rs", "crores", "₹ in lakhs") failed validation | Units are normalised before validation |

### Changes in agents-v10 (38-question run with v9: 27/38 correct)
| Finding | Fix |
| --- | --- |
| A result unit the schema did not know (q015) failed the whole Analyst call | Unknown result units become empty and the calculator infers them (`* 100` → %, money inputs → Rs crore) |
| Variable labels written slightly differently from the extracted labels (q023: "operating profit FY24" vs "Operating Profit (FY24)") | Labels are matched ignoring case, spaces and brackets |
| A margin question answered with a money figure (q028 gave Rs 5,340.61 crore instead of 22.0%) | For margin, %, share or growth questions the Analyst must return a % (or x) result, otherwise it is sent back once |

New test scripts (no change for P4): `refusal_check.py` (section 4c) and `text_eval.py` (section 4d).

### Changes in agents-v10.1 (refusal check 4c: 11/12 refused, 18/18 answered)
| Finding | Fix |
| --- | --- |
| "Rank Amul, Patanjali and HUL by profitability" was classed as an in-scope ranking (q080) | After the Gatekeeper, code refuses any request that names a company outside the covered list (`out_of_scope`). No change to how P4 calls `run_gatekeeper` |

### Changes in agents-v10.2 (text check 4d: 5 of 10 brief sections lost to Critic errors)
| Finding | Fix |
| --- | --- |
| The Critic invented problem labels ("misleading", "missing data"), so a valid section was thrown away | Unknown labels are mapped to the nearest allowed one; unknown `fix_owner` becomes "writer" |
| A Critic quote that was never found in the draft failed the whole answer | `run_critic` never raises now: the draft is kept, rule checks still run, and `CriticOutput.verified = False`. **P4: when `verified` is False, show the answer with a short "not independently checked" note** |
