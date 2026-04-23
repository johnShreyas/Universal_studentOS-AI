# ══════════════════════════════════════════════════════════
#  service.py — Student OS Autonomous Orchestrator
#
#  This is the "brain" of the system. It decides HOW to
#  answer every student question by running this logic:
#
#  1. Search local vector store (student's own notes)
#  2. Score the result — is it good enough to answer?
#  3. If NOT sufficient → decide: web search or YouTube?
#  4. Fetch external data using the right tool
#  5. Synthesise everything into one cited response
#  6. Stream it back to the UI
#
#  The app.py never calls Gemini directly — it calls this.
# ══════════════════════════════════════════════════════════
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Generator, Optional

from helpers import (
    WebSearchTool, YouTubeTool, ResponseFormatter,
    stream_response, generate_once,
)
from config import GEMINI_KEYS, TOP_K, MIN_SCORE


# ══════════════════════════════════════════════════════════
#  DATA CLASSES
# ══════════════════════════════════════════════════════════

@dataclass
class ToolCall:
    """Records which tools were triggered and why."""
    tool:   str   # "local" | "web" | "youtube" | "grounded"
    reason: str
    query:  str


@dataclass
class OrchestratorResult:
    """Everything the UI needs to render one response."""
    full_response:  str
    tools_used:     list[ToolCall]  = field(default_factory=list)
    sources:        list[dict]      = field(default_factory=list)
    used_local:     bool            = False
    used_web:       bool            = False
    used_youtube:   bool            = False


# ══════════════════════════════════════════════════════════
#  DECISION ENGINE
# ══════════════════════════════════════════════════════════

# Keywords that signal the student wants a YouTube explanation
YOUTUBE_SIGNALS = [
    "youtube", "video", "watch", "explain visually",
    "video tutorial", "lecture", "watch a video",
]

# Keywords that signal real-time web data is needed
WEB_SIGNALS = [
    "latest", "recent", "current", "today", "news", "2024", "2025", "2026",
    "research paper", "new study", "just released", "this year", "update",
    "who is", "what happened", "price of", "when did",
]

# Threshold: if local notes cover >= this fraction of the query,
# skip external search
LOCAL_SUFFICIENCY_SCORE = 0.55


def _classify_query(query: str) -> dict:
    """
    Analyse a query and return a decision dict:
    {
        needs_web:      bool,
        needs_youtube:  bool,
        youtube_url:    str | None,   # if student pasted a URL
        search_query:   str,          # cleaned query for web search
    }
    """
    q_lower = query.lower()

    # Extract YouTube URL if present
    yt_url = None
    yt_match = re.search(
        r"(https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w\-]+)",
        query,
    )
    if yt_match:
        yt_url = yt_match.group(1)

    needs_youtube = yt_url is not None or any(s in q_lower for s in YOUTUBE_SIGNALS)
    needs_web     = any(s in q_lower for s in WEB_SIGNALS)

    # Build a clean search query (remove meta-words)
    search_query = re.sub(
        r"\b(youtube|video|watch|latest news about|current|search for|find me)\b",
        "", query, flags=re.IGNORECASE,
    ).strip()

    return {
        "needs_web":     needs_web,
        "needs_youtube": needs_youtube,
        "youtube_url":   yt_url,
        "search_query":  search_query or query,
    }


def _local_context_sufficient(results: list[dict]) -> bool:
    """
    Returns True if local notes are relevant enough
    to answer without external tools.
    """
    if not results:
        return False
    top_score = max(r.get("score", 0) for r in results)
    return top_score >= LOCAL_SUFFICIENCY_SCORE


# ══════════════════════════════════════════════════════════
#  ORCHESTRATOR
# ══════════════════════════════════════════════════════════

class StudentOSOrchestrator:
    """
    The autonomous research agent.

    Usage:
        orch = StudentOSOrchestrator(memory=warrior_memory)
        for chunk in orch.stream("explain quantum entanglement"):
            print(chunk, end="")

        result = orch.last_result   # OrchestratorResult with metadata
    """

    def __init__(self, memory=None):
        """
        Args:
            memory: WarriorMemory instance (from vector_store.py).
                    Can be None if no documents have been loaded.
        """
        self.memory      = memory
        self.web_tool    = WebSearchTool()
        self.yt_tool     = YouTubeTool()
        self.formatter   = ResponseFormatter()
        self.last_result : Optional[OrchestratorResult] = None

    def stream(
        self,
        query: str,
        key_index: int = 0,
    ) -> Generator[str, None, None]:
        """
        Main entry point. Yields text chunks for streaming to UI.
        Sets self.last_result after completion.

        Flow:
            query → classify → check local → [web/youtube if needed]
                  → build prompt → stream Gemini → yield chunks
        """
        tools_used   : list[ToolCall] = []
        sources      : list[dict]     = []
        context_parts: list[str]      = []

        classification = _classify_query(query)

        # ── Step 1: Search local vector store ─────────────
        local_context = ""
        used_local    = False

        if self.memory and self.memory.count() > 0:
            try:
                local_results = self.memory.search(query, top_k=TOP_K)
                if local_results:
                    local_context = self.memory.format_context(
                        local_results, min_score=MIN_SCORE
                    )
                    if local_context:
                        context_parts.append(
                            "## 📚 From Your Notes\n" + local_context
                        )
                        used_local = True
                        tools_used.append(ToolCall(
                            tool   = "local",
                            reason = "Student has relevant uploaded notes",
                            query  = query,
                        ))
            except Exception:
                pass

        # ── Step 2: Decide if external tools needed ────────
        local_sufficient = _local_context_sufficient(
            self.memory.search(query, top_k=1) if (self.memory and self.memory.count() > 0) else []
        )

        # ── Step 3a: YouTube tool ──────────────────────────
        used_youtube = False
        if classification["needs_youtube"]:
            yt_url = classification["youtube_url"]

            if not yt_url:
                # No URL given — search for one
                search_results = self.web_tool.search(
                    f"youtube {classification['search_query']} tutorial explanation",
                    max_results=3,
                )
                yt_url = next(
                    (r["url"] for r in search_results if "youtube" in r["url"]),
                    None,
                )

            if yt_url:
                summary = self.yt_tool.summarise(yt_url, query, key_index)
                if summary and not summary.startswith("Could not"):
                    context_parts.append(
                        self.yt_tool.format_for_prompt(summary, yt_url)
                    )
                    sources.append({"type": "youtube", "url": yt_url})
                    used_youtube = True
                    tools_used.append(ToolCall(
                        tool   = "youtube",
                        reason = "Student requested video explanation",
                        query  = query,
                    ))

        # ── Step 3b: Web search tool ───────────────────────
        used_web = False
        if classification["needs_web"] or not local_sufficient:
            web_results = self.web_tool.search(
                classification["search_query"],
                max_results=5,
            )
            if web_results and web_results[0]["score"] > 0:
                context_parts.append(
                    self.web_tool.format_for_prompt(web_results)
                )
                sources.extend([
                    {"type": "web", "url": r["url"], "title": r["title"]}
                    for r in web_results if r["url"]
                ])
                used_web = True
                tools_used.append(ToolCall(
                    tool   = "web",
                    reason = (
                        "Query requires real-time data"
                        if classification["needs_web"]
                        else "Local notes insufficient — augmenting with web"
                    ),
                    query  = classification["search_query"],
                ))

        # ── Step 4: Build final prompt ─────────────────────
        from datetime import datetime
        today = datetime.now().strftime("%B %d, %Y")

        prompt_parts = [f"TODAY: {today}\n"]

        if context_parts:
            prompt_parts.append("# RESEARCH CONTEXT\n")
            prompt_parts.extend(context_parts)
            prompt_parts.append("\n---\n")

        prompt_parts.append(f"# STUDENT QUESTION\n{query}")

        if context_parts:
            prompt_parts.append(
                "\n\nINSTRUCTION: Synthesise ALL context above into one "
                "unified, well-cited answer. Cite sources inline using "
                "[Your Notes: filename] or [Web: title] or [Video: url]."
            )

        final_prompt = "\n".join(prompt_parts)

        # ── Step 5: Stream Gemini response ─────────────────
        full_response = ""
        use_pro       = used_web or used_youtube  # use Pro when reasoning over sources

        try:
            for chunk in stream_response(
                prompt          = final_prompt,
                key_index       = key_index,
                use_pro         = use_pro,
                use_grounded_search = False,  # we do our own search above
            ):
                cleaned = ResponseFormatter.clean(chunk) if chunk else ""
                if cleaned:
                    full_response += cleaned
                    yield cleaned

        except Exception as e:
            err = f"\n\n⚠️ Error: {e}"
            full_response += err
            yield err

        # ── Step 6: Store metadata ─────────────────────────
        self.last_result = OrchestratorResult(
            full_response = full_response,
            tools_used    = tools_used,
            sources       = sources,
            used_local    = used_local,
            used_web      = used_web,
            used_youtube  = used_youtube,
        )
