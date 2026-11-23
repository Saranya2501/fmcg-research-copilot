# FMCG Copilot integration issues and token usage

23 November 2026

Review for the P1 evaluation, P2 prompting, P3 retrieval and P5 deployment teams. The two most urgent defects affect trust in every research answer: the embedding client can send credentials without verifying the server certificate, and the final answer writer can lose a comparison company’s evidence. Both should be resolved before team sign-off.

### What the current checkout establishes

The local corpus contains 113,405 chunks with 377 distinct document IDs. The P5 and P4 integration suites passed 62 tests with local dotenv loading disabled. The bundled P2 agent suite passed 28 checks. These checks establish component behavior. Production answer accuracy, page-level citation quality and typical token cost still need a representative end-to-end run.

### What one short question cost

The saved question “tell me hul FY22” produced a one-sentence revenue answer after eight model calls. It used 23,025 tokens against a 24,000-token turn budget. Two validation repairs alone used 8,647 tokens. The next page reconciles every call with the saved turn total.

### Decisions for the team

P3 should correct certificate handling. P2 and the P4 runtime maintainer should preserve evidence across subtasks. P1 should establish a repeatable answer-level baseline before P5 changes the routing or token budget. P5 can then compare a shorter single-metric route against the same questions and citations.

### Evidence and limits

This review combines local source inspection, dataset inspection, regression tests, and historical usage records. The detailed token example is an observed turn on 22 November. No new paid evaluation, Docker image build, or production load test was performed for this report. Prior failures are identified separately from defects reproduced on the current checkout.

Evidence locations below are relative to the repository root. Local chat history and call logs are excluded from Git.

## Model usage for the HUL turn

The 22,328 displayed input tokens accumulated across the following calls. Each row is a successful model response recorded in the local call log. Every row had one transport attempt and zero model-cache hits.

| Stage | Input | Output | Total |
| --- | ---: | ---: | ---: |
| Gatekeeper | 916 | 69 | 985 |
| Planner | 863 | 92 | 955 |
| Query writer | 524 | 42 | 566 |
| Analyst | 3,655 | 97 | 3,752 |
| Analyst repair | 4,111 | 122 | 4,233 |
| Writer | 3,771 | 90 | 3,861 |
| Writer repair | 4,242 | 172 | 4,414 |
| Critic | 4,246 | 13 | 4,259 |
| Entire turn | 22,328 | 697 | 23,025 |

### Why the total grew

Input accounted for 97.0% of the turn. The first three calls consumed 2,506 tokens before analysis. The analyst, writer and critic received three passages each. The application estimated 1,424 passage tokens per stage, or 4,272 across their first attempts. This estimate excludes repair replays, instructions, schemas and intermediate results. It is already included in the measured totals.

The two repairs accounted for 37.6% of the turn. Each repair appended the invalid reply and validation feedback to the original messages, replaying the existing context. The log identifies the repair stages but does not establish the precise validation rule that failed. Removing those calls would save 8,647 tokens only if both first attempts became valid and other calls stayed the same.

The turn left 975 tokens of budget. Earlier records also include HTTP 401 and 429 responses and a saved budget-exhaustion outcome. Those are separate runs. No transport retries explain the eight successful calls above. Provider billing rates and representative traffic are unavailable, so a currency estimate or typical cost would be speculative.

*Evidence: p5-deployment/data/logs/llm_calls.jsonl, 22:25:31 through 22:25:52 on 22 November; p5-deployment/data/chat_history.sqlite3; p4-agent/integration/p2_agents/json_utils.py, call_json.*

## P1 evaluation and acceptance evidence

### The gold inventory and handoff disagree

The P1 README describes 80 questions and names gold_v1.jsonl. The checked-in file is gold_v1_with_context.jsonl and contains 100 rows: UC1 20, UC2 18, UC3 30, UC4 5, UC5 5, UC6 10 and UC7 12. A team member following the README can select the wrong input or report the wrong denominator. Update the reference, publish the dataset revision, and print counts by use case in every evaluation.

### Evidence fields are empty across the dataset

All 100 rows have empty context fields. Numeric examples still carry expected values, source descriptions and pages, so they can support answer scoring. An isolated prompt evaluation that expects source passages will receive none. Keep refusal rows eligible for an empty context and measure how many evidence-bearing rows resolve to text on the intended page.

The P3 enrichment script imports the initial chunk-map variable directly. The loader later assigns a populated dictionary in the retrieval module. The enrichment function can therefore keep seeing the initial empty state. It also compares short gold document IDs to full indexed IDs and assumes numeric pages where the gold file includes strings. Fix these before regenerating the dataset; verify a known page against its report.

### Answer quality and refusal behavior need separate scores

The P1 directory lists an end-to-end runner, injection tests and schema artifacts as expected deliverables. Its current contents are the README and gold file. A P1 contract exists elsewhere under P4 references; the P3 recall script evaluates retrieval. No completed, reproducible scorecard for the full P5 answer path was identified. Treat that as a verification gap.

Record numeric tolerance, unit, reporting period, company, and cited page for each financial answer. Separate source-present questions, source-absent questions and the 12 UC7 refusal cases. Include injection fixtures in the safety evaluation and save failure counts. A reference to a report alone cannot establish that a number is correct.

*Inspect: p1-eval/README.md; p1-eval/gold_v1_with_context.jsonl; p3-retrieval/eval/recall_eval.py, get_context_from_parsed and evaluate; p4-agent/references/P1_RESPONSE_AND_EVIDENCE_CONTRACT.md.*

## P2 prompting and research orchestration

### Simple lookups take the full research route

P5 calls the bundled P2 implementation under p4-agent/integration/p2_agents/. The separate p2-prompting directory contains a handoff README. The active P4 runner invokes the gatekeeper and planner, then a query writer and analyst per subtask with evidence, followed by a final writer and critic. This explains why a short user input can generate many long model inputs. Larger plans can multiply the middle stages.

Evaluate a shorter route for a single company, metric and year. Require the cited passage to support the value, period, unit and reporting basis. An ambiguous request such as “tell me hul FY22” names no metric. Test a clarification path or an explicit metric assumption alongside an unambiguous revenue question. Route comparisons, arithmetic and conflicting evidence through the longer workflow.

### Repair prompts replay the original context

P2 permits two repair calls after an invalid first response. Corrections can benefit from the full evidence when a factual claim is wrong. A formatting-only issue can require much less context. Count repairs by agent and validation rule. Apply deterministic fixes for well-defined format errors; preserve evidence-based checks for factual corrections. Test the accepted value and its citation after any change.

### Comparison evidence can disappear before verification

The active P4 runner keeps up to five chunks per subtask, then selects only the first five unique chunks across all subtasks for the writer and critic. If company A supplies five distinct chunks, company B’s analyst results can reach both agents without B’s supporting passages. This is a correctness defect shared by the P2 and P5 integration, with the selection code owned by P4.

Select cited chunk IDs from the reported results first. Allocate remaining space across companies and periods, and mark an unsupported result explicitly when the evidence budget cannot fit it. Regression case: provide two companies with five distinct chunks each and verify that a claim about each company reaches the critic with its own cited passage.

*Inspect: p4-agent/integration/runtime.py, run_query and the evidence slice at line 109; p4-agent/integration/p2_agents/config.py and json_utils.py; p5-deployment/integrations/agent_bridge.py, run_agent.*

## P3 retrieval and corpus coverage

### Embedding requests can bypass certificate verification

The runtime retrieval module resolves CACERT_PATH, then sets HTTP verification to False if the path is missing. The embedding request still sends the query and bearer key. A missing certificate mount or filename typo therefore weakens transport security. Reject an invalid configured path before sending the request. Permit system trust for endpoints configured to use publicly trusted certificates. Test missing, valid private-CA and system-trust configurations.

### Metadata filters and corpus labels disagree

The local parsed corpus contains only annual_report and quarterly_results document-type labels. P2 can request investor_presentation, press_release or call_transcript, and P3 compares filter values exactly. Such a filter can discard a relevant presentation indexed under quarterly_results. Four companies have annual-report labels only: Dabur, Marico, Emami and Colgate-Palmolive India. Nestle India has no FY23 annual-report label. Distinguish absent source material from source material indexed under a broader type.

P3 also takes the top 100 global candidates from each search method before applying metadata filters. Matching chunks outside both windows never enter reranking. Evaluate scoped queries with known evidence, then compare filtering earlier or expanding candidate windows. Report the effect on recall and latency.

### Published recall measures document discovery

The integration guide reports recall@5 of 0.795 and recall@10 of 0.830 on 88 non-refusal questions. The evaluator can infer company and year from the gold source, and a matching document ID counts as a hit regardless of page. These scores cannot establish live query-filter accuracy or financial answer correctness. Run a second benchmark using only filters available from the user question and measure cited-page accuracy.

The guide reports 406 PDFs. The installed parsed data yielded 377 unique document IDs across 113,405 chunks. PDFs and indexed IDs are different units. Reconcile them against a source manifest before attributing the difference to missing or duplicate files. For table questions, test amount, column year and consolidated or standalone basis against the source page; the guide records frequent low-confidence text fallbacks.

*Inspect: p4-agent/p3_retrieval/retrieve.py, lines 58 and 225–237; p3-retrieval/INTEGRATION.md; p3-retrieval/eval/recall_eval.py; p4-agent/p3_retrieval/parsed/all_chunks.jsonl.*

## P5 operations and verification plan

### Environment-dependent tests and poor failure feedback

A previous ordinary P5 test run in this checkout had nine failures when app imports loaded the local .env. With dotenv disabled, the current P5 and P4 integration run passed 62 tests. Isolate the test environment before application imports. Verify a plain test invocation on machines with and without a configured .env.

Saved research failures name the stopped stage. The local logs include authentication failures and rate limiting, which need different recovery actions. Map provider status to a short user-facing explanation and retain sanitized diagnostic details for operators. Validate each outcome with a simulated provider response and confirm partial turns retain their measured token totals.

### Session recovery and deployment status

The previous New chat resume defect is fixed. Creating the conversation in the button callback lets the first rerun save the new ID. The regression test reproduced the stale value before the change and now passes. Earlier browser testing also found that on a narrow viewport, choosing a history item can leave the sidebar covering the selected answer. Retest selection at mobile width and dismiss the overlay once navigation succeeds.

The pass count covers local integration and Streamlit tests. Compose configuration validated in the earlier review. A clean image build followed by an authenticated research turn through the running container is still outstanding. Check read-only corpus mounts, certificate paths, persisted history and a source citation after container restart.

### How to measure the token fix

Use the same model, index, prompts and gold questions for a baseline and a candidate run. Group results by factual lookup, clarification, comparison, calculation and refusal. Record prompt and completion tokens, repairs, model calls, cache hits, latency, budget stops and answer quality. Run cold and warm caches separately. Report median and 95th-percentile usage with the sample size for each group.

Start with TLS verification and evidence retention. Then establish P1 scores before changing prompts or routing. Adopt a shorter lookup route only when the measured token reduction preserves value, unit, period and citation accuracy on the agreed test set. Keep the observed 23,025-token case as a regression example; choose a production budget from broader measurements.

*Inspect: p5-deployment/app.py; ui/sidebar.py; tests/test_user_sessions.py; integrations/agent_bridge.py; docker-compose.yml (all under p5-deployment/).*
