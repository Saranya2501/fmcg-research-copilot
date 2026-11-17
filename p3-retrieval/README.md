# P3 — Retrieval

Owner: Saranya

Corpus ingestion, chunking, hybrid BM25+FAISS retrieval, reranking, and the `retrieve()` / `get_table()` interface for P4.

See **INTEGRATION.md** for full setup instructions, output schemas, filter keys, and corpus status.

## Files

| File | Purpose |
|---|---|
| `parse_corpus.py` | Parse all PDFs in Corpus → chunked JSONL in `parsed/` |
| `build_index.py` | Build BM25 + FAISS indexes from `parsed/all_chunks.jsonl` |
| `retrieve.py` | `retrieve()` and `get_table()` — import this in P4 |
| `eval/recall_eval.py` | Recall@k evaluation harness |
| `INTEGRATION.md` | Integration guide for P4 (Rohit) |
| `.env.template` | Copy to `.env` and fill in API keys |

## Index files

Too large for git (~300 MB total). Download from the shared Drive folder and place at:

```
p3-retrieval/index/bm25.pkl
p3-retrieval/index/faiss.index
p3-retrieval/index/chunk_ids.json
```

Or rebuild locally (~20 min):

```bash
venv/bin/python3 build_index.py
```
