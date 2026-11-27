# P4 implementation notes

This package is based on the actual `P4_Project_Files` nested in the received P4.zip. It retains the P4 ownership boundary and updates the starter implementation to match the 10-day plan.

## P4 workflow
Gatekeeper → Planner → Researcher → Executor → Analyst → Writer → Critic. The Critic may request up to two repair rounds. A failed schema validation after the repair limit returns a controlled partial response.

The planner supports the original `steps` format and a `subtasks` format. P2 should confirm the final plan schema before the prompts are frozen.

## Seven tools
1. `search_reports` — P3 retrieval adapter.
2. `get_table` — P3 table extraction adapter.
3. `calculator` — safe arithmetic expression evaluator.
4. `unit_convert` — crore/lakh/million/billion conversion.
5. `company_lookup` — ten-company aliases; ITC includes an FMCG-segment caution.
6. `metric_lookup` — starter synonym mapping.
7. `generate_report` — DOCX export behind explicit approval.

## Guards
- Gatekeeper before retrieval.
- 10-step execution cap.
- 6,000-token graph budget when P2 reports token usage.
- 45-second tool timeout.
- Repeated-call detection.
- Up to two critic repair rounds.
- Response schema validation.
- Retrieved content labelled as untrusted data.
- Human approval for report export.

P2's shared client remains responsible for the single-request queue, 2/4/8-second retries, CA verification, and Qwen3 thinking-off default. P4 does not duplicate those controls.

## Known integration gaps
P2/P3/P5 implementation code was not present in the uploaded archives. P3's ten company ZIPs contain report PDFs, not the retrieval/index source code. The P4 adapter is therefore ready for binding but not connected to a live index.
