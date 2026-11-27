# P4 Submission Package — Status and Team Dependencies

## P4 deliverables included
- P4 LangGraph workflow, state, schemas, tools, guardrails, and tests.
- Python runtime integration layer and CLI (`app/run_research.py`), using the P2 agent interface and P3 retrieval adapter.
- P2 agent source/interface retained under `integration/p2_agents/` for the current integration baseline.
- P3 retrieval source and index bundle retained under `core/`.
- P1 gold dataset/evidence contract and P3 corpus manifest retained in `data/` and `references/` where supplied.
- Documentation, test suite, Colab/setup materials.

## Pending external deliverables / replacement instructions
1. **P3 full parsed corpus:** provide `parsed/all_chunks.jsonl`; the chunk sample is not the full corpus. Place it in the P3 runtime structure alongside the index artifacts. The P3 `retrieve.py` must resolve the corpus/index from its expected directory.
2. **P3 runtime assembly:** confirm `retrieve.py`, `index/`, and `parsed/all_chunks.jsonl` are together in the runtime folder and run retrieval tests. The index bundle is retained but has not been validated against a complete corpus in this package.
3. **P2 final package/config:** P2 owner should supply approved final agents, schemas/config, client credentials/config instructions and dependency versions. Reconcile with `integration/p2_agents/`; preserve or adapter-map the runtime API. No credentials should be committed.
4. **P5 deliverables:** UI, tracing, eval runner, and deployment integration are not verified/included as completed P5 artifacts. P5 can consume the P4 Python runtime contract; integrate their source when delivered.
5. **Live integrated evaluation:** execute end-to-end with configured model, full P3 corpus and the P1 gold set; record citation/value/unit/FY checks and results. Offline tests alone do not establish this.

## Folder handoff structure
`handoff/P2/`, `handoff/P3/parsed/`, `handoff/P3/index/`, and `handoff/P5/` are designated staging folders for owner files. Reconcile incoming files into canonical locations rather than blindly replacing them.

## Verification
The package's offline automated tests are the only verification claimed here. Live API, complete-corpus retrieval, and integrated P1 gold-set evaluation are pending.
