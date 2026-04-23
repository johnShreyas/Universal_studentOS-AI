# ══════════════════════════════════════════════════════════
#  vector_store.py — Student OS Local Memory
#
#  ChromaDB: 100% local, no cloud account needed.
#  Embeddings: Google text-embedding-004 (new genai SDK)
#
#  pip install chromadb google-genai
#
#  CLI:
#    python vector_store.py add   notes/lecture.pdf
#    python vector_store.py search "what is entropy"
#    python vector_store.py list
#    python vector_store.py clear
# ══════════════════════════════════════════════════════════
import os
import hashlib
from typing import List

import chromadb
from chromadb.config import Settings
from google import genai
from google.genai import types

from ingestion import load_and_split
from config import (
    GEMINI_KEYS, CHROMA_PATH, COLLECTION_NAME,
    EMBED_MODEL, TOP_K, MIN_SCORE,
)


# ══════════════════════════════════════════════════════════
#  EMBEDDINGS
# ══════════════════════════════════════════════════════════

EMBED_BATCH_SIZE = 2


def embed_texts(texts: List[str], api_key: str) -> List[List[float]]:
    """Batch-embed a list of text strings → list of float vectors."""
    client = genai.Client(api_key=api_key)
    all_embeddings = []

    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch    = texts[i : i + EMBED_BATCH_SIZE]
        response = client.models.embed_content(
            model    = EMBED_MODEL,
            contents = batch,
            config   = types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
        )
        for emb in response.embeddings:
            all_embeddings.append(emb.values)

    return all_embeddings


def embed_query(query: str, api_key: str) -> List[float]:
    """Embed a single query string for similarity search."""
    client   = genai.Client(api_key=api_key)
    response = client.models.embed_content(
        model    = EMBED_MODEL,
        contents = [query],
        config   = types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
    )
    return response.embeddings[0].values


# ══════════════════════════════════════════════════════════
#  STUDENT MEMORY
# ══════════════════════════════════════════════════════════

class StudentMemory:
    """
    The student's personal research memory.
    Stores chunks from any uploaded document and retrieves
    the most relevant paragraphs for any question.
    """

    def __init__(self, api_key: str = "", persist_path: str = CHROMA_PATH):
        self.api_key = api_key or GEMINI_KEYS[0]

        self.client = chromadb.PersistentClient(
            path     = persist_path,
            settings = Settings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name     = COLLECTION_NAME,
            metadata = {"hnsw:space": "cosine"},
        )
        print(f"[StudentMemory] Ready — {self.collection.count()} chunks stored")

    # ── Add documents ──────────────────────────────────────

    def add_documents(self, path: str, force: bool = False) -> int:
        """
        Load a file or folder, embed all chunks, save to ChromaDB.
        Returns number of new chunks added.
        """
        chunks = load_and_split(path)
        if not chunks:
            return 0

        ids, texts, metadatas = [], [], []

        for chunk in chunks:
            chunk_id = _stable_id(
                chunk.metadata.get("filename", ""),
                chunk.metadata.get("page_number", 1),
                chunk.metadata.get("chunk_index", 0),
                chunk.page_content,
            )
            if not force and self._exists(chunk_id):
                continue

            ids.append(chunk_id)
            texts.append(chunk.page_content)
            metadatas.append({
                "filename":    chunk.metadata.get("filename", "unknown"),
                "page_number": str(chunk.metadata.get("page_number", 1)),
                "chunk_index": str(chunk.metadata.get("chunk_index", 0)),
                "source":      chunk.metadata.get("source", ""),
            })

        if not ids:
            print("[StudentMemory] All chunks already stored.")
            return 0

        print(f"[StudentMemory] Embedding {len(ids)} chunks…")
        embeddings = embed_texts(texts, self.api_key)

        for i in range(0, len(ids), 100):
            self.collection.upsert(
                ids        = ids[i : i + 100],
                embeddings = embeddings[i : i + 100],
                documents  = texts[i : i + 100],
                metadatas  = metadatas[i : i + 100],
            )

        print(f"[StudentMemory] ✅ {len(ids)} new chunks. Total: {self.collection.count()}")
        return len(ids)

    # ── Search ─────────────────────────────────────────────

    def search(self, query: str, top_k: int = TOP_K) -> List[dict]:
        """
        Find the most relevant chunks for a question.
        Returns list of {text, filename, page_number, score}.
        """
        if self.collection.count() == 0:
            return []

        query_vector = embed_query(query, self.api_key)
        n            = min(top_k, self.collection.count())

        results   = self.collection.query(
            query_embeddings = [query_vector],
            n_results        = n,
            include          = ["documents", "metadatas", "distances"],
        )

        output = []
        for text, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            output.append({
                "text":        text,
                "filename":    meta.get("filename", "unknown"),
                "page_number": int(meta.get("page_number", 1)),
                "chunk_index": int(meta.get("chunk_index", 0)),
                "score":       round(1 - dist, 4),
            })

        return output

    # ── Format for prompt ──────────────────────────────────

    def format_context(
        self, results: List[dict], min_score: float = MIN_SCORE
    ) -> str:
        """Format relevant chunks as a string for prompt injection."""
        relevant = [r for r in results if r["score"] >= min_score]
        if not relevant:
            return ""
        parts = []
        for r in relevant:
            header = f"[Your Notes: {r['filename']}, Page {r['page_number']}]"
            parts.append(f"{header}\n{r['text'].strip()}")
        return "\n\n".join(parts)

    # ── Management ─────────────────────────────────────────

    def list_sources(self) -> List[str]:
        if self.collection.count() == 0:
            return []
        all_meta = self.collection.get(include=["metadatas"])["metadatas"]
        return sorted({m.get("filename", "unknown") for m in all_meta})

    def remove_source(self, filename: str) -> int:
        all_data = self.collection.get(include=["metadatas"])
        ids_to_delete = [
            id_ for id_, meta in zip(all_data["ids"], all_data["metadatas"])
            if meta.get("filename") == filename
        ]
        if ids_to_delete:
            self.collection.delete(ids=ids_to_delete)
        return len(ids_to_delete)

    def clear_all(self):
        self.client.delete_collection(COLLECTION_NAME)
        self.collection = self.client.get_or_create_collection(
            name     = COLLECTION_NAME,
            metadata = {"hnsw:space": "cosine"},
        )
        print("[StudentMemory] All memory cleared.")

    def count(self) -> int:
        return self.collection.count()

    def _exists(self, chunk_id: str) -> bool:
        return len(self.collection.get(ids=[chunk_id])["ids"]) > 0


# ══════════════════════════════════════════════════════════
#  UTILITY
# ══════════════════════════════════════════════════════════

def _stable_id(filename: str, page: int, index: int, text: str) -> str:
    raw = f"{filename}::{page}::{index}::{text[:100]}"
    return hashlib.md5(raw.encode()).hexdigest()


# ══════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys

    try:
        import streamlit as st
        api_key = st.secrets["GEMINI_PRIMARY"]
    except Exception:
        import os
        api_key = os.environ.get("GEMINI_PRIMARY", "")

    if not api_key:
        print("❌ Set GEMINI_PRIMARY in .streamlit/secrets.toml or env")
        sys.exit(1)

    mem     = StudentMemory(api_key=api_key)
    command = sys.argv[1] if len(sys.argv) > 1 else "help"

    if command == "add" and len(sys.argv) > 2:
        added = mem.add_documents(sys.argv[2], force="--force" in sys.argv)
        print(f"✅ Added {added} chunks")

    elif command == "search" and len(sys.argv) > 2:
        query   = " ".join(sys.argv[2:])
        results = mem.search(query)
        for i, r in enumerate(results, 1):
            print(f"\n[{i}] Score:{r['score']} | {r['filename']} p.{r['page_number']}")
            print(r["text"][:300])

    elif command == "list":
        for s in mem.list_sources():
            print(f"  • {s}")
        print(f"\nTotal: {mem.count()} chunks")

    elif command == "clear":
        if input("Clear ALL memory? (yes): ").strip().lower() == "yes":
            mem.clear_all()
    else:
        print("Usage: python vector_store.py add|search|list|clear [args]")
