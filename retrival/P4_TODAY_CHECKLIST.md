# P4 execution checklist — 16 Nov 2026

## Completed in the P4 package
- [x] LangGraph orchestration and seven-tool registry.
- [x] Shared state, step limit, token-budget hook, timeout, repeated-call guard and repair limit.
- [x] P1 response contract validation and approval-gated DOCX export.
- [x] Retrieval adapter updated to the P3 guide's `retrieve(query, k, filters)` and `get_table(doc_id, page, section_hint)` API.
- [x] Unit tests: 18 passed in the package test run (`PYTHONPATH=. pytest -q`).

## P4 work to finish
1. Obtain P3's actual RAG source/index directory and set `RetrievalAdapter.from_p3_path(...)`.
2. Obtain P2's agent prompt callbacks and bind them to `build_graph(...)`.
3. Confirm P1's final UC1–UC7, brief template, aliases and frozen gold set.
4. Connect P5 tracing and eval runner; attach run metadata and results.
5. Run end-to-end tests for lookup, table extraction, calculation, comparison, follow-up, refusal, injection, missing evidence, malformed JSON, tool failure/timeout and approval gate.
6. Record measured results and unresolved limitations; do not report mocked tests as live retrieval tests.

## Send to the group
See `integration/OWNER_HANDOFF.md` for the exact outstanding deliverables by owner.
