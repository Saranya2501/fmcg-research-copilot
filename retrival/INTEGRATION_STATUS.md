# Integration status

## P4 deliverable scope
- P4 LangGraph workflow and seven-tool registry retained from the verified local package.
- Baseline: 18 P4 tests previously passed on the user Mac. Package-refresh verification in this environment: 20 tests passed (18 P4 + 2 runtime normalization tests).
- Graph compilation: passed (user-reported).
- P2 agent package (`agents-v3` package containing agents-v4 prompts/config) copied under `integration/p2_agents` for integration reference and runtime loading.
- `integration/runtime.py` is a conservative, callable P2/P3 research path. It is tested only for chunk normalization (2 tests); not claimed to be tested against live services yet.
- Gold dataset copy included for local test harness/reference; no evaluation API calls are run automatically.

## Required before live end-to-end run
1. P3's actual Python source directory containing `retrieve.py`, `build_index.py`, `requirements.txt` and any runtime dependencies. The supplied guide/index/corpus archives alone do not provide `retrieve.py`.
2. P2's configured LLM target and credential/certificate setup. Do not place credentials in this repository.
3. P5's trace/evaluation/app deployment package (the P5 ZIP supplied was empty).

## Index
The large index ZIP is supplied separately by P3. Keep it outside Git/repository archives; unpack into the P3 RAG project's `index/` directory. Do not re-build unless P3 instructs.
