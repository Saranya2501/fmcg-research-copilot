# P3 integration status (updated 26 November 2026)

## Available and included
- P3 retrieval implementation: `p4-agent/core/retrieve.py` (repository-root path).
- Matching hybrid indexes and the full `parsed/all_chunks.jsonl` are supplied separately through the [shared Drive folder](https://drive.google.com/drive/folders/1-WKMvaOx8v3jJAcwN_jSKkMa3AHC1OR-).
- P4 `RetrievalAdapter.from_p3_path()` can import the P3 API once its runtime files are placed correctly.

## Data placement for live retrieval

The P3 source reads `index/` and `parsed/all_chunks.jsonl` relative to its own
directory. Download and extract both the indexes and parsed chunks from Drive.
The parsed corpus is required for filtering, citations/chunk lookup, and
`get_table()`; a sample file is not a substitute.

Expected runtime layout:
```
p4-agent/core/
  retrieve.py
  index/
    bm25.pkl
    faiss.index
    chunk_ids.json
  parsed/
    all_chunks.jsonl
```

The P3 embedding API is optional: when `IITK_EMBED_URL` and `IITK_EMBED_KEY` are absent, P3 falls back to its local SentenceTransformer embedding model. The reranker also loads locally. These model downloads can be large and first-run latency is expected.

The locally verified data bundle on 26 November 2026 contained 117,194 chunks,
482 distinct document IDs, and no duplicate chunk IDs. Both local P3 directories
had identical copies of all four data files. These checks do not verify the
Drive upload or live retrieval/model responses; use the same complete rebuilt
bundle when preparing the download.

See the [P5 guide](../../p5-deployment/README.md#iitk-institute-api) for LLM and
embedding credentials, CA certificates, and Docker-specific certificate paths.
