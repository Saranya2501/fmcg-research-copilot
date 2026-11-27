# P3 integration status (updated 20 Nov 2026)

## Available and included
- P3 retrieval implementation: `p3_retrieval/retrieve.py`
- P3 hybrid retrieval index archive was supplied separately (`index/bm25.pkl`, `index/faiss.index`, `index/chunk_ids.json`).
- P4 `RetrievalAdapter.from_p3_path()` can import the P3 API once its runtime files are placed correctly.

## Still required for live retrieval
The P3 source reads `index/` and `parsed/all_chunks.jsonl` relative to its own directory. The supplied index archive contains the three index files, but not `parsed/all_chunks.jsonl`. That parsed chunk corpus is required for `_load_index()` and for filtering, citations/chunk lookup and `get_table()`.

Expected runtime layout:
```
p3_retrieval/
  retrieve.py
  index/
    bm25.pkl
    faiss.index
    chunk_ids.json
  parsed/
    all_chunks.jsonl
```

The P3 embedding API is optional: when `IITK_EMBED_URL` and `IITK_EMBED_KEY` are absent, P3 falls back to its local SentenceTransformer embedding model. The reranker also loads locally. These model downloads can be large and first-run latency is expected.

This package does not claim live retrieval until `parsed/all_chunks.jsonl` is supplied and a retrieval smoke test succeeds.
