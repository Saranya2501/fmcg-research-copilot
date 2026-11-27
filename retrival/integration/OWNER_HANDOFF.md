# Owner handoff — P4 integration status (16 Nov 2026)

## P1 — specification and evaluation
Received: product/use-case specifications, refusal policy, scoring rules, gold-set draft, injection/refusal tests, evaluation methodology and report material.

P4 contract uses outcome values `answered`, `partial`, `clarification_needed`, `refused`, `not_found`. Numeric acceptance is ±1% for non-zero values; unit, fiscal period, reporting basis and page citation must also match.

**P1 confirmation still needed**
1. Freeze/confirm UC1–UC7 and the seven-section brief template against the Scope tab.
2. Confirm canonical company names/aliases and the permitted company list.
3. Confirm the gold set version is frozen and identify the approved gold-set path.
4. Confirm whether any project scope changes are approved (especially FY scope and corpus target).

## P2 — model client received; agent prompts still needed
Received: `P2_LLM_Client.ipynb` and `P2_Baseline.ipynb`. The shared client exposes `LLMClient().chat(messages, tag=..., max_tokens=..., temperature=..., thinking=..., tools=..., tool_choice=..., response_format=...)`; result includes `text`, `raw_text`, `tool_calls`, `usage`, `latency_s`, `finish_reason`, `cached`, and `target`.

**P2 items still needed**
1. Runnable/exported `llm_client.py` plus `.env.example` (no secrets) and `requirements.txt`, or confirm the notebook is the canonical source.
2. Production agent prompt/function interfaces for Gatekeeper, Planner, Researcher/query rewriting, Analyst, Writer, Critic and JSON repair. Baseline prompts alone do not implement these graph callbacks.
3. For each callback: exact signature, expected return schema, and one sample input/output.
4. Confirm model/token limits per agent and whether tool-call responses use the same `LLMClient.chat()` interface.
5. Confirm the shared API queue, CA certificate configuration, 2/4/8-second retry behaviour and 429/503 handling are tested in the delivered client.

## P3 — integration guide received; implementation package still needed
Received: ten company archives and `INTEGRATION.md`. The guide documents:
- `from retrieve import retrieve, get_table`
- `retrieve(query=..., k=5, filters={...})`
- `get_table(doc_id=..., page=..., section_hint=...)`
- retrieval records containing `doc_id`, `company`, `fiscal_year`, `doc_type`, `section`, `page`, `standalone_consolidated`, `text`, `score`
- table result with `headers`, `rows`, `low_confidence` and optional `text_fallback`
- 406 PDFs and 113,405 chunks in the reported index.

P4 adapter has now been aligned to this documented API and can import from the RAG directory using `RetrievalAdapter.from_p3_path(rag_path)`.

**P3 items still needed**
1. Actual RAG source package/folder containing `retrieve.py`, `build_index.py`, `requirements.txt` and the prebuilt `index/` files (or a reproducible build package).
2. Confirm the shared index is the latest index and includes the corpus listed in the guide.
3. One tested `retrieve()` and `get_table()` call from the supplied environment, including a real `doc_id` carried from retrieval to table extraction.
4. Confirm page-number convention (PDF physical page vs printed page) and exact `get_table()` return shape for no table / low-confidence cases.
5. Confirm retrieval filters and values exactly as documented.
6. Provide recall@5/recall@10 results and retrieval-hit vs miss evaluation.
7. Resolve the guide's listed corpus gaps: Nestlé FY23 annual report; quarterly results/presentations for Dabur, Marico, Emami and Colgate. Confirm whether these are available elsewhere or formally out of scope.

**Corpus status from P3 guide:** 406 PDFs / 113,405 chunks; Nestlé FY23 annual report marked missing; quarterly/presentation coverage marked pending for Dabur, Marico, Emami and Colgate. The earlier ten archive inspection found annual-report-only PDFs in those ZIPs; the P3 guide is the source for the wider indexed corpus status.

## P5 — implementation files still needed
The uploaded P5 archive did not contain usable implementation source.

Please provide:
1. Langfuse initialization and trace/span API.
2. Evaluation runner entry point and output CSV/JSON schema.
3. Streamlit app entry point and exact graph invocation interface.
4. Docker Compose file, service names, volumes and environment variables.
5. Cache/rate-limit interfaces and metric recording contract (latency, token use, tool calls, completion, refusal).

## P4 delivery boundary
P4 owns LangGraph orchestration, seven tool schemas/registry, shared state, guards, response validation, retrieval adapter and approval-gated DOCX export. P4 does not own P2 prompt design/client implementation, P3 indexing/retrieval internals, or P5 tracing/UI/deployment.
