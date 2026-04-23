# ══════════════════════════════════════════════════════════
#  config.py — Student OS Configuration
#  Universal student assistant — subject agnostic
#
#  Required in .streamlit/secrets.toml:
#    GEMINI_PRIMARY   = "AIza..."
#    GEMINI_BACKUP    = "AIza..."
#    TAVILY_API_KEY   = "tvly-..."   # https://tavily.com (free tier available)
# ══════════════════════════════════════════════════════════
import streamlit as st

# ── Gemini API Keys (rotate on 429) ───────────────────────
GEMINI_KEYS = [
    st.secrets["GEMINI_PRIMARY"],
    st.secrets["GEMINI_BACKUP"],
]

# ── Tavily Web Search API Key ──────────────────────────────
TAVILY_KEY = st.secrets.get("TAVILY_API_KEY", "")

# ── Models ─────────────────────────────────────────────────
MODEL_FLASH = "gemini-2.5-flash"   # default — fast, high rate limit
MODEL_PRO   = "gemini-2.5-pro"     # reasoning — used when tools activate
EMBED_MODEL = "text-embedding-004" # Google embeddings for vector store

# ── Vector Store ───────────────────────────────────────────
CHROMA_PATH     = "student_memory"
COLLECTION_NAME = "student_notes"
TOP_K           = 5     # chunks retrieved per query
MIN_SCORE       = 0.30  # minimum relevance score to include chunk

# ── Ingestion ──────────────────────────────────────────────
CHUNK_SIZE    = 1000
CHUNK_OVERLAP = 200

# ── Supported upload types ─────────────────────────────────
SUPPORTED_EXTENSIONS = [
    "pdf", "txt", "md",          # documents
    "docx",                       # Word
    "csv",                        # data / notes
    "py", "js", "ts", "java",    # code files (CS students)
    "tex",                        # LaTeX papers
]

# ── PDF output ─────────────────────────────────────────────
PDF_TRIGGER_WORDS = [
    "pdf", "question sheet", "question paper", "practice sheet",
    "practice question", "mock test", "question bank",
    "worksheet", "notes pdf", "summary pdf",
]

INTENT_TRIGGER_WORDS = [
    "genrat", "generat", "make", "create", "give", "send",
    "prepare", "provide", "get me", "write me",
]

PDF_YES_WORDS = [
    "yes", "yeah", "yep", "sure", "ok", "okay",
    "please", "do it", "generate", "make it", "download",
]

# ── Session defaults ───────────────────────────────────────
SESSION_DEFAULTS = {
    "messages":       [],
    "pending_pdf":    None,
    "pdf_ready":      False,
    "queued_msg":     None,
    "last_pdf_query": "",
}
