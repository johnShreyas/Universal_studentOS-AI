# ══════════════════════════════════════════════════════════
#  helpers.py — Student OS Toolbox
#
#  Contains:
#    WebSearchTool   — Tavily real-time web search
#    YouTubeTool     — fetch & summarise video transcripts
#    ResponseFormatter — enforce Turbo-style Markdown + LaTeX
#    PDF utilities   — build and trigger downloadable PDFs
#
#  SDK: google-genai (2026 unified)
#  pip install google-genai tavily-python youtube-transcript-api
# ══════════════════════════════════════════════════════════
import re
import streamlit as st
from typing import Optional
from google import genai
from google.genai import types

from config import (
    GEMINI_KEYS, TAVILY_KEY,
    PDF_TRIGGER_WORDS, INTENT_TRIGGER_WORDS, PDF_YES_WORDS,
    MODEL_FLASH, MODEL_PRO,
)
from prompt import SYSTEM_PROMPT
from pdf_generator import create_pro_pdf


# ══════════════════════════════════════════════════════════
#  🔍 WEB SEARCH TOOL — Tavily
# ══════════════════════════════════════════════════════════

class WebSearchTool:
    """
    Real-time web search using Tavily API.
    Returns structured results with titles, URLs, and content.

    Free tier: 1000 searches/month — https://tavily.com
    """

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or TAVILY_KEY
        self._client = None

    def _get_client(self):
        if not self._client:
            try:
                from tavily import TavilyClient
                self._client = TavilyClient(api_key=self.api_key)
            except ImportError:
                raise ImportError("Run: pip install tavily-python")
        return self._client

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        """
        Search the web for query.
        Returns list of {title, url, content, score}.
        Falls back gracefully if API key not set.
        """
        if not self.api_key:
            return [{
                "title":   "Web search not configured",
                "url":     "",
                "content": "Add TAVILY_API_KEY to .streamlit/secrets.toml to enable web search.",
                "score":   0.0,
            }]

        try:
            client   = self._get_client()
            response = client.search(
                query              = query,
                max_results        = max_results,
                search_depth       = "advanced",
                include_answer     = True,
                include_raw_content= False,
            )
            results = []
            for r in response.get("results", []):
                results.append({
                    "title":   r.get("title", ""),
                    "url":     r.get("url", ""),
                    "content": r.get("content", "")[:800],
                    "score":   r.get("score", 0.0),
                })
            return results

        except Exception as e:
            return [{"title": "Search error", "url": "", "content": str(e), "score": 0.0}]

    def format_for_prompt(self, results: list[dict]) -> str:
        """Format search results for injection into AI prompt."""
        if not results:
            return ""
        lines = ["## 🔍 Web Search Results\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"**[{i}] {r['title']}**")
            if r["url"]:
                lines.append(f"URL: {r['url']}")
            lines.append(r["content"])
            lines.append("")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════
#  🎬 YOUTUBE TOOL
# ══════════════════════════════════════════════════════════

class YouTubeTool:
    """
    Fetches YouTube video transcripts and summarises them.
    No API key needed — uses youtube-transcript-api.
    pip install youtube-transcript-api
    """

    def get_transcript(self, video_url: str) -> str:
        """Extract transcript from a YouTube URL or video ID."""
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
        except ImportError:
            return "Run: pip install youtube-transcript-api"

        # Extract video ID from URL
        video_id = self._extract_id(video_url)
        if not video_id:
            return f"Could not extract video ID from: {video_url}"

        try:
            transcript = YouTubeTranscriptApi.get_transcript(video_id)
            # Join all text chunks
            full_text = " ".join(chunk["text"] for chunk in transcript)
            return full_text[:8000]  # cap at 8k chars to fit in prompt
        except Exception as e:
            return f"Could not fetch transcript: {e}"

    def summarise(self, video_url: str, query: str, key_index: int = 0) -> str:
        """
        Fetch transcript + ask Gemini to summarise it
        in the context of the student's question.
        """
        transcript = self.get_transcript(video_url)

        if transcript.startswith("Run:") or transcript.startswith("Could not"):
            return transcript

        summary_prompt = (
            f"The student is studying: {query}\n\n"
            f"Here is the transcript of a YouTube video:\n\n{transcript}\n\n"
            "Please summarise the key points relevant to the student's topic. "
            "Use bullet points. Keep it under 300 words."
        )

        try:
            client   = genai.Client(api_key=GEMINI_KEYS[key_index])
            response = client.models.generate_content(
                model    = MODEL_FLASH,
                contents = summary_prompt,
                config   = types.GenerateContentConfig(
                    system_instruction = SYSTEM_PROMPT,
                ),
            )
            return response.text or "Could not summarise transcript."
        except Exception as e:
            return f"Summarisation error: {e}"

    def _extract_id(self, url: str) -> str:
        """Extract YouTube video ID from various URL formats."""
        patterns = [
            r"(?:v=|youtu\.be/|embed/|shorts/)([a-zA-Z0-9_-]{11})",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        # If it looks like a raw ID already
        if re.match(r"^[a-zA-Z0-9_-]{11}$", url):
            return url
        return ""

    def format_for_prompt(self, summary: str, video_url: str) -> str:
        """Format YouTube summary for prompt injection."""
        return (
            f"## 🎬 Video Transcript Summary\n"
            f"**Source:** {video_url}\n\n"
            f"{summary}\n"
        )


# ══════════════════════════════════════════════════════════
#  ✨ RESPONSE FORMATTER
# ══════════════════════════════════════════════════════════

class ResponseFormatter:
    """
    Post-processes AI responses to enforce Turbo-style formatting:
    - Removes raw backtick code blocks from non-code responses
    - Ensures LaTeX delimiters are correct for Streamlit
    - Strips filler phrases
    """

    FILLER_PHRASES = [
        r"Great question[!.]?\s*",
        r"Sure[!,]?\s*",
        r"Absolutely[!,]?\s*",
        r"Of course[!,]?\s*",
        r"I hope this helps[.!]?\s*",
        r"Feel free to ask[^.]*[.!]?\s*",
        r"As an AI[^.]*\.\s*",
    ]

    @classmethod
    def clean(cls, text: str) -> str:
        """Remove backticks and filler phrases."""
        # Remove triple-backtick blocks (not code blocks — we want LaTeX rendered)
        text = re.sub(r"```(?!python|js|java|c\+\+|cpp|sql|bash|sh)[\s\S]*?```", "", text)
        # Remove inline backticks for math (we use $ instead)
        text = re.sub(r"`([^`\n]+)`", r"\1", text)
        # Remove filler phrases
        for phrase in cls.FILLER_PHRASES:
            text = re.sub(phrase, "", text, flags=re.IGNORECASE)
        return text.strip()

    @classmethod
    def add_streaming_cursor(cls, text: str) -> str:
        """Add blinking cursor during streaming."""
        return cls.clean(text) + "▌"


# ══════════════════════════════════════════════════════════
#  GEMINI CLIENT HELPERS
# ══════════════════════════════════════════════════════════

def get_client(key_index: int = 0) -> genai.Client:
    return genai.Client(api_key=GEMINI_KEYS[key_index])


def make_config(
    use_grounded_search: bool = False,
    system_instruction: str = SYSTEM_PROMPT,
) -> types.GenerateContentConfig:
    """Build GenerateContentConfig with optional Google Search grounding."""
    tools = None
    if use_grounded_search:
        tools = [types.Tool(google_search=types.GoogleSearch())]
    return types.GenerateContentConfig(
        system_instruction = system_instruction,
        tools              = tools,
    )


def stream_response(
    prompt: str,
    key_index: int = 0,
    use_pro: bool = False,
    use_grounded_search: bool = False,
):
    client = get_client(key_index)
    # We force it to Flash if we want to avoid 429s during testing
    model  = MODEL_PRO if use_pro else MODEL_FLASH 
    config = make_config(use_grounded_search=use_grounded_search)

    try:
        for chunk in client.models.generate_content_stream(
            model    = model,
            contents = prompt,
            config   = config,
        ):
            if chunk.text:
                yield chunk.text
    except Exception as e:
        # 🛡️ THE FIX: If Pro hits a limit, switch to Flash instantly
        if "429" in str(e) and use_pro:
            st.toast("⚡ Pro limit hit! Switching to Flash engine...", icon="🚀")
            for chunk in client.models.generate_content_stream(
                model    = MODEL_FLASH,
                contents = prompt,
                config   = config,
            ):
                if chunk.text:
                    yield chunk.text
        else:
            raise e


def generate_once(prompt: str, key_index: int = 0) -> str:
    """Single non-streaming call. Returns full text."""
    client   = get_client(key_index)
    response = client.models.generate_content(
        model    = MODEL_FLASH,
        contents = prompt,
        config   = make_config(),
    )
    return response.text or ""


# ══════════════════════════════════════════════════════════
#  PDF DETECTION & BUILDING
# ══════════════════════════════════════════════════════════

def user_wants_pdf(query: str) -> bool:
    q = query.lower()
    return (
        any(w in q for w in PDF_TRIGGER_WORDS) and
        any(w in q for w in INTENT_TRIGGER_WORDS)
    )


def user_said_yes_to_pdf(query: str) -> bool:
    q = query.lower().strip()
    return len(q.split()) <= 6 and any(w in q for w in PDF_YES_WORDS)


def ai_offered_pdf(messages: list) -> bool:
    """True only if the last AI message before current input offered a PDF."""
    user_skipped = False
    for msg in reversed(messages):
        if msg["role"] == "user" and not user_skipped:
            user_skipped = True
            continue
        if msg["role"] == "assistant":
            return "would you like me to save these as a pdf" in msg["content"].lower()
        if msg["role"] == "user":
            return False
    return False


def get_last_ai_questions(messages: list) -> str:
    for msg in reversed(messages):
        if msg["role"] == "assistant" and "1." in msg["content"]:
            return msg["content"]
    return ""


def build_pdf_and_show(content: str, title: str = "Student OS — Practice Sheet"):
    """Build PDF from content and show download button."""
    with st.spinner("⚡ Building your PDF…"):
        pdf_bytes = create_pro_pdf(content, title)
        st.session_state.pending_pdf    = pdf_bytes
        st.session_state.pdf_ready      = True
        st.session_state.last_pdf_query = title

    st.success(f"✅ **PDF Ready!** — {title}")
    st.download_button(
        label="📥 Download Now",
        data=pdf_bytes,
        file_name="StudentOS_Sheet.pdf",
        mime="application/pdf",
        use_container_width=True,
        key="pdf_inline_btn",
    )
