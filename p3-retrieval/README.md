# P3 — Retrieval

Owner: Saranya

Corpus ingestion, chunking, hybrid BM25+FAISS retrieval, reranking, and the `retrieve()` / `get_table()` interface for P4.

See [INTEGRATION.md](INTEGRATION.md) for standalone setup, output schemas,
filter keys, and corpus notes. To run the full Streamlit application, start with
the [repository quick start](../README.md#run-the-full-application).

## Files

| File | Purpose |
|---|---|
| `parse_corpus.py` | Parse all PDFs in Corpus → chunked JSONL in `parsed/` |
| `build_index.py` | Build BM25 + FAISS indexes from `parsed/all_chunks.jsonl` |
| `retrieve.py` | `retrieve()` and `get_table()` — import this in P4 |
| `eval/recall_eval.py` | Recall@k evaluation harness |
| `INTEGRATION.md` | Integration guide for P4 (Rohit) |
| `.env.template` | Copy to `.env` and fill in API keys |

## Index files and parsed chunks

Download the matching indexes and full parsed chunks from the
[shared Drive folder](https://drive.google.com/drive/folders/1-WKMvaOx8v3jJAcwN_jSKkMa3AHC1OR-).
For standalone P3 retrieval, place them at:

```
p3-retrieval/index/bm25.pkl
p3-retrieval/index/faiss.index
p3-retrieval/index/chunk_ids.json
p3-retrieval/parsed/all_chunks.jsonl
```

The default P5 Streamlit app instead reads these files from
`p4-agent/p3_retrieval/index/` and `p4-agent/p3_retrieval/parsed/`.
Use one matching bundle; index files alone and sample chunks are insufficient.

To rebuild standalone P3 indexes, first supply `parsed/all_chunks.jsonl` and
install the P3 dependencies. From `p3-retrieval/`:

```bash
venv/bin/python3 build_index.py
```

The builder skips existing indexes. Rebuilding after changing parsed chunks
requires moving the previous index files aside first, then generating all three
index files together. The full source PDFs are needed only when re-parsing the
corpus; they are not required for retrieval from an existing complete bundle.
