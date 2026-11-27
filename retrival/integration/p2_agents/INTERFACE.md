# P2 → P4 interface: LLM client and agents (agents-v4)

Everything P4 needs to wire the agent graph. All examples use the fictional company Example Foods.

## 1. Files

| File | What it is |
| --- | --- |
| `llm_client.py` | Shared Qwen3-8B client: API or local Ollama, CA cert, one-at-a-time lock, retries, cache, call log |
| `config.py` | All limits: tokens, timeouts, retries, JSON repairs, loop guards, evidence budget, covered companies |
| `schemas.py` | Pydantic input/output models for every agent |
| `json_utils.py` | `call_json()`: JSON mode → local fixes → schema validation → grounding check → up to 2 repairs |
| `agents.py` | One function per agent (below) |
| `prompts/*.md` | Prompt files, versioned as `agents-v4`; `_shared.md` is prepended to each |
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
