# P3 files checklist for current P4

Included in this package:
- retrieve.py (P3 retrieval implementation)
- index_bundle.zip (BM25, FAISS, chunk_ids)

Still required for live retrieval:
- parsed/all_chunks.jsonl (P3 parsed chunk corpus)

Optional:
- IITK embedding API URL/key; source has a local SentenceTransformer fallback.
- CACERT_PATH certificate if using the embedding API and the API requires it.

The full Annual Reports archive is not required at runtime if the index and parsed chunks are provided; it is mainly source corpus/rebuild material.

P5 tracing, evaluation runner, app/deployment source remain outstanding.
