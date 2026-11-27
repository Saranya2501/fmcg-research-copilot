# Python entry point

This wrapper runs the integrated P2/P3 answer path (not the dummy graph smoke test).

Set paths to extracted P2 agent files and the P3 runtime directory:

```bash
export P2_PACKAGE_PATH=/path/to/p2_agents_v3
export P3_RAG_PATH=/path/to/p3_rag
python -m app.run_research "Compare HUL advertising expenses FY24 and FY25"
```

P3 runtime path must contain `retrieve.py`, `index/`, and `parsed/all_chunks.jsonl` in the layout expected by P3. Configure P2 model credentials using P2's documented environment variables. Do not commit credentials.
