# ══════════════════════════════════════════════════════════
#  ingestion.py — Universal Document Ingestion Pipeline
#  Supports: PDF, TXT, MD, DOCX, CSV, code files, LaTeX
# ══════════════════════════════════════════════════════════
import os
from pathlib import Path
from typing import List

from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    UnstructuredMarkdownLoader,
    UnstructuredWordDocumentLoader,
    CSVLoader,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from config import CHUNK_SIZE, CHUNK_OVERLAP, SUPPORTED_EXTENSIONS


SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size      = CHUNK_SIZE,
    chunk_overlap   = CHUNK_OVERLAP,
    separators      = ["\n\n", "\n", ". ", " ", ""],
    length_function = len,
)

# Extension → loader mapping
LOADER_MAP = {
    ".pdf":  "pdf",
    ".txt":  "text",
    ".md":   "markdown",
    ".docx": "docx",
    ".csv":  "csv",
    # Code files and LaTeX — treat as plain text
    ".py":   "text", ".js":  "text", ".ts":  "text",
    ".java": "text", ".cpp": "text", ".c":   "text",
    ".tex":  "text", ".sql": "text", ".sh":  "text",
}


def _load_file(filepath: str) -> List[Document]:
    """Load a single file into Document objects."""
    path     = Path(filepath)
    ext      = path.suffix.lower()
    filename = path.name
    loader_type = LOADER_MAP.get(ext, "text")

    try:
        if loader_type == "pdf":
            loader = PyPDFLoader(filepath)
        elif loader_type == "markdown":
            loader = UnstructuredMarkdownLoader(filepath)
        elif loader_type == "docx":
            loader = UnstructuredWordDocumentLoader(filepath)
        elif loader_type == "csv":
            loader = CSVLoader(filepath)
        else:
            loader = TextLoader(filepath, encoding="utf-8")

        docs = loader.load()

    except Exception as e:
        # Fallback to plain text for any unsupported loader
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            docs = [Document(page_content=content, metadata={})]
        except Exception:
            print(f"  ❌ Could not load {filename}: {e}")
            return []

    # Normalise metadata
    for i, doc in enumerate(docs):
        doc.metadata["source"]      = filepath
        doc.metadata["filename"]    = filename
        doc.metadata["file_type"]   = ext.lstrip(".")
        doc.metadata["page_number"] = doc.metadata.get("page", i) + 1

    return docs


def _split_and_tag(raw_docs: List[Document]) -> List[Document]:
    chunks  = SPLITTER.split_documents(raw_docs)
    counter = {}
    for chunk in chunks:
        fname = chunk.metadata.get("filename", "unknown")
        counter[fname]             = counter.get(fname, 0) + 1
        chunk.metadata["chunk_index"] = counter[fname]
    return chunks


def load_and_split(path: str) -> List[Document]:
    """
    Load any supported file or folder and return split chunks.
    Each chunk: .page_content + .metadata{filename, page_number, chunk_index, file_type}
    """
    target = Path(path)

    if target.is_dir():
        files = []
        for ext in SUPPORTED_EXTENSIONS:
            files.extend(target.glob(f"**/*.{ext}"))
        if not files:
            print(f"[ingestion] No supported files in: {path}")
            return []
        print(f"[ingestion] Found {len(files)} file(s)")
    elif target.is_file():
        files = [target]
    else:
        raise FileNotFoundError(f"Path not found: {path}")

    raw_docs = []
    for filepath in sorted(files):
        docs = _load_file(str(filepath))
        if docs:
            raw_docs.extend(docs)
            print(f"  ✅ {filepath.name} ({len(docs)} sections)")

    if not raw_docs:
        return []

    chunks = _split_and_tag(raw_docs)
    total_chars = sum(len(c.page_content) for c in chunks)
    print(f"\n[ingestion] {len(raw_docs)} sections → {len(chunks)} chunks "
          f"(avg {total_chars // max(len(chunks), 1)} chars)")
    return chunks


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "DATA/"
    docs = load_and_split(path)
    for doc in docs[:3]:
        print(f"\n{doc.metadata['filename']} p.{doc.metadata['page_number']}")
        print(doc.page_content[:200])
