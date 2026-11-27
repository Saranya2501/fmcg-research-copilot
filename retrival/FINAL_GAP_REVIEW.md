# Final gap review — current P4 package

## Included/available now
- P4 LangGraph graph, shared state, guards, tool registry, schemas, and tests.
- P2 agent implementation and prompts included in the current package integration folder (agent/model-client interface).
- P3 `retrieve.py` source included in `p3_retrieval/`.
- P3 index bundle (BM25, FAISS, chunk-ID mapping) included as a ZIP.
- P3 corpus manifest and P1 response/evidence contract.
- Sample chunk file supplied on 22 Nov 2026 added under `demo_data/`. This is a sample, not asserted to be the full corpus.
- Integration runner `integration/runtime.py` documents and implements a direct P2/P3 integrated answer path; model calls are made via the P2 `LLMClient`/agent functions.

## Still needed / not verified
1. Full P3 parsed corpus `parsed/all_chunks.jsonl` (the uploaded `chunks_sample_p2.jsonl` is a sample only; its size/coverage does not establish that it is the full corpus).
2. P3 runtime directory layout and index extracted together with parsed corpus so `retrieve.py` can load its expected `index/` and `parsed/` folders.
3. Credentials/configuration for P2 model and, if desired, P3 embedding service. Never put secrets in this ZIP; use environment variables.
4. A live end-to-end run with P2 model + P3 retrieval (not yet verified in this package build).
5. P5 Streamlit/UI, observability, evaluation runner and deployment source; P5 is not included in this package.
6. Execute gold evaluation set against the integrated live system and report retrieval/answer metrics.

## Notebooks vs Python
Notebooks are retained for setup/testing/demo. Application/integration code is Python modules and should be imported by the UI. No notebook is required as the runtime entry point.
