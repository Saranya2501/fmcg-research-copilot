"""
M4: Build BM25 (rank_bm25) and FAISS (bge-small-en-v1.5) indexes from parsed chunks.
Saves:
  index/bm25.pkl          — BM25Okapi instance + id list
  index/faiss.index       — FAISS IndexFlatIP (inner product = cosine after L2 norm)
  index/chunk_ids.json    — ordered list of chunk_ids matching FAISS rows
"""

import json
import os
import pickle
import warnings
from pathlib import Path

import faiss
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

warnings.filterwarnings("ignore")

RAG_DIR = Path(__file__).resolve().parent
PARSED_DIR = RAG_DIR / "parsed"
INDEX_DIR = RAG_DIR / "index"
INDEX_DIR.mkdir(exist_ok=True)

COMBINED_JSONL = PARSED_DIR / "all_chunks.jsonl"
MODEL_NAME = "BAAI/bge-small-en-v1.5"
BATCH_SIZE = 128   # encode this many chunks at a time


def load_chunks() -> list[dict]:
    print(f"Loading chunks from {COMBINED_JSONL}…")
    chunks = []
    with open(COMBINED_JSONL) as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    print(f"  {len(chunks):,} chunks loaded.")
    return chunks


def tokenize(text: str) -> list[str]:
    """Simple whitespace+punctuation tokenizer for BM25."""
    import re
    return re.sub(r"[^\w\s]", " ", text.lower()).split()


def build_bm25(chunks: list[dict]) -> None:
    out_path = INDEX_DIR / "bm25.pkl"
    if out_path.exists():
        print("BM25 index already exists — skipping.")
        return

    print("Building BM25 index…")
    corpus_tokens = [tokenize(c["text"]) for c in tqdm(chunks, desc="Tokenizing")]
    bm25 = BM25Okapi(corpus_tokens)
    chunk_ids = [c["chunk_id"] for c in chunks]

    with open(out_path, "wb") as f:
        pickle.dump({"bm25": bm25, "chunk_ids": chunk_ids}, f)
    print(f"  BM25 index saved → {out_path}  ({os.path.getsize(out_path)/1e6:.1f} MB)")


def build_faiss(chunks: list[dict]) -> None:
    faiss_path = INDEX_DIR / "faiss.index"
    ids_path = INDEX_DIR / "chunk_ids.json"
    if faiss_path.exists() and ids_path.exists():
        print("FAISS index already exists — skipping.")
        return

    print(f"Loading embedding model: {MODEL_NAME} …")
    model = SentenceTransformer(MODEL_NAME)
    dim = model.get_sentence_embedding_dimension()
    print(f"  Embedding dim: {dim}")

    index = faiss.IndexFlatIP(dim)   # inner product — vectors will be L2-normalised
    chunk_ids = []
    texts = [c["text"] for c in chunks]

    print(f"Encoding {len(texts):,} chunks in batches of {BATCH_SIZE}…")
    for i in tqdm(range(0, len(texts), BATCH_SIZE), desc="Encoding"):
        batch = texts[i : i + BATCH_SIZE]
        embeddings = model.encode(batch, normalize_embeddings=True, show_progress_bar=False)
        embeddings = np.array(embeddings, dtype=np.float32)
        index.add(embeddings)
        chunk_ids.extend(c["chunk_id"] for c in chunks[i : i + BATCH_SIZE])

    faiss.write_index(index, str(faiss_path))
    with open(ids_path, "w") as f:
        json.dump(chunk_ids, f)

    print(f"  FAISS index saved → {faiss_path}  ({os.path.getsize(faiss_path)/1e6:.1f} MB)")
    print(f"  chunk_ids saved  → {ids_path}")
    print(f"  Total vectors: {index.ntotal:,}")


def main():
    chunks = load_chunks()
    build_bm25(chunks)
    build_faiss(chunks)
    print("\nM4 done. Index files:")
    for f in sorted(INDEX_DIR.iterdir()):
        print(f"  {f.name}  {os.path.getsize(f)/1e6:.1f} MB")


if __name__ == "__main__":
    main()
