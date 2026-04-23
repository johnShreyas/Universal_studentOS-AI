# ══════════════════════════════════════════════════════════
#  app.py — Student OS Entry Point
#  Run with: streamlit run app.py
#
#  Architecture:
#    app.py  →  service.py (brain)
#                ├── vector_store.py (local memory)
#                ├── helpers.WebSearchTool (Tavily)
#                └── helpers.YouTubeTool (transcripts)
# ══════════════════════════════════════════════════════════
import os
import tempfile
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime

from config import SESSION_DEFAULTS, GEMINI_KEYS, SUPPORTED_EXTENSIONS
from helpers import (
    ResponseFormatter,
    user_wants_pdf, user_said_yes_to_pdf,
    ai_offered_pdf, get_last_ai_questions,
    build_pdf_and_show,
)


# ══════════════════════════════════════════════════════════
#  PAGE CONFIG
# ══════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Student OS",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ══════════════════════════════════════════════════════════
#  CACHED RESOURCES
# ══════════════════════════════════════════════════════════

@st.cache_resource(show_spinner=False)
def get_memory():
    """Load student memory once. Returns None if ChromaDB not set up."""
    try:
        from vector_store import StudentMemory
        return StudentMemory(api_key=GEMINI_KEYS[0])
    except Exception:
        return None


@st.cache_resource(show_spinner=False)
def get_orchestrator():
    """Create orchestrator once and reuse."""
    from service import StudentOSOrchestrator
    return StudentOSOrchestrator(memory=get_memory())


# ══════════════════════════════════════════════════════════
#  GLOBAL CSS
# ══════════════════════════════════════════════════════════
st.markdown("""
<style>
/* ── Chat text ── */
[data-testid="stChatMessage"] p,
[data-testid="stChatMessage"] li,
[data-testid="stChatMessage"] td {
    font-size: 16px !important;
    line-height: 1.8 !important;
}
[data-testid="stChatMessage"] strong { font-size: 16px !important; }
[data-testid="stChatMessage"] h1 { font-size: 26px !important; }
[data-testid="stChatMessage"] h2 { font-size: 22px !important; }
[data-testid="stChatMessage"] h3 { font-size: 18px !important; }

/* ── Sidebar ── */
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] span { font-size: 14px !important; }

/* ── Input bar ── */
[data-testid="stChatInput"] { position: relative !important; }
[data-testid="stChatInput"] textarea {
    font-size: 16px !important;
    padding-right: 56px !important;
    border-radius: 28px !important;
}
[data-testid="stChatInput"] button[data-testid="stChatInputSubmitButton"] {
    opacity: 0 !important;
    pointer-events: none !important;
    transition: opacity 0.15s !important;
}
[data-testid="stChatInput"].has-text
button[data-testid="stChatInputSubmitButton"] {
    opacity: 1 !important;
    pointer-events: auto !important;
}

/* ── Mic ── */
#ew-mic-btn {
    position: absolute; right: 10px; top: 50%;
    transform: translateY(-50%); z-index: 9999;
    background: none; border: none; font-size: 20px;
    cursor: pointer; color: #888; padding: 4px 6px;
    border-radius: 8px; transition: color 0.15s; line-height: 1;
}
#ew-mic-btn:hover { color: #ccc; }
[data-testid="stCheckbox"] {
    display: none !important; height: 0 !important; overflow: hidden !important;
}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════
#  SESSION STATE
# ══════════════════════════════════════════════════════════
if "app_initialized" not in st.session_state:
    st.session_state.clear()
    st.session_state.app_initialized = True
    st.session_state.show_settings   = False
    st.session_state.show_voice      = False
    for k, v in SESSION_DEFAULTS.items():
        st.session_state[k] = v
else:
    for k, v in SESSION_DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = v
    for key, default in [("show_settings", False), ("show_voice", False)]:
        if key not in st.session_state:
            st.session_state[key] = default

st.session_state.show_settings = False


def start_new_chat():
    for k in SESSION_DEFAULTS:
        st.session_state[k] = SESSION_DEFAULTS[k]
    st.session_state.pdf_ready      = False
    st.session_state.pending_pdf    = None
    st.session_state.last_pdf_query = ""
    st.session_state.queued_msg     = None
    st.session_state.show_voice     = False


# ══════════════════════════════════════════════════════════
#  SIDEBAR
# ══════════════════════════════════════════════════════════
with st.sidebar:

    st.markdown("""
    <div style='display:flex; align-items:center; gap:10px; padding:8px 0 4px;'>
        <span style='font-size:28px;'>🎓</span>
        <div>
            <div style='font-size:17px; font-weight:600;'>Student OS</div>
            <div style='font-size:11px; color:#888;'>Universal Research Agent</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    if st.button("✏️  New Chat", use_container_width=True, key="new_chat_btn"):
        start_new_chat()
        st.rerun()

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # ── Memory status ──────────────────────────────────────
    memory = get_memory()
    if memory and memory.count() > 0:
        sources = memory.list_sources()
        st.markdown(
            f"<div style='padding:8px 12px; border-radius:8px; "
            f"background:rgba(0,200,100,0.08); border:1px solid rgba(0,200,100,0.2); "
            f"font-size:12px; color:#4caf7d;'>"
            f"📚 {memory.count()} chunks · {len(sources)} file(s) loaded</div>",
            unsafe_allow_html=True,
        )
        with st.expander("📂 Loaded sources", expanded=False):
            for src in sources:
                col_a, col_b = st.columns([4, 1])
                with col_a:
                    st.caption(f"📄 {src}")
                with col_b:
                    if st.button("✕", key=f"rm_{src}", help=f"Remove {src}"):
                        removed = memory.remove_source(src)
                        st.cache_resource.clear()
                        st.success(f"Removed {removed} chunks")
                        st.rerun()
            if st.button("🗑 Clear all memory", key="clear_all_mem",
                          use_container_width=True):
                memory.clear_all()
                st.cache_resource.clear()
                st.rerun()
    else:
        st.markdown("""
        <div style='padding:10px 12px; border-radius:8px;
             border:1px dashed rgba(255,255,255,0.15);
             font-size:12px; color:#555; text-align:center;'>
            No notes loaded yet.<br>Upload any document below ↓
        </div>
        """, unsafe_allow_html=True)

    # ── Universal file upload ──────────────────────────────
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    with st.expander("➕ Upload Study Material", expanded=False):
        st.caption(f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}")
        uploaded_files = st.file_uploader(
            "Upload any document",
            type=SUPPORTED_EXTENSIONS,
            accept_multiple_files=True,
            key="doc_uploader",
            label_visibility="collapsed",
        )
        if uploaded_files:
            if st.button("📥 Add to memory", key="add_docs_btn",
                          use_container_width=True):
                from vector_store import StudentMemory
                mem = StudentMemory(api_key=GEMINI_KEYS[0])
                total_added = 0

                with st.status("Processing documents…", expanded=True) as status:
                    for uploaded in uploaded_files:
                        ext      = os.path.splitext(uploaded.name)[1]
                        tmp_path = None
                        try:
                            with tempfile.NamedTemporaryFile(
                                delete=False, suffix=ext
                            ) as tmp:
                                tmp.write(uploaded.read())
                                tmp_path = tmp.name

                            st.write(f"⚙️ Processing {uploaded.name}…")
                            added = mem.add_documents(tmp_path)
                            total_added += added
                            st.write(f"✅ {uploaded.name} — {added} chunks")

                        except Exception as e:
                            st.write(f"❌ {uploaded.name}: {e}")
                        finally:
                            if tmp_path and os.path.exists(tmp_path):
                                os.unlink(tmp_path)

                    status.update(
                        label=f"Done! Added {total_added} chunks total.",
                        state="complete",
                    )

                st.cache_resource.clear()
                st.rerun()

    # ── Bottom icons ───────────────────────────────────────
    st.markdown("<div style='height:10vh'></div>", unsafe_allow_html=True)
    st.divider()

    ic1, ic2, ic3, ic4 = st.columns(4)
    with ic1:
        if st.button("⚙️", use_container_width=True, key="settings_btn", help="Settings"):
            st.session_state.show_settings = not st.session_state.show_settings
    with ic2:
        if st.button("🌙", use_container_width=True, key="theme_btn", help="Theme"):
            st.toast("Theme toggle coming soon!", icon="🌙")
    with ic3:
        if st.button("❓", use_container_width=True, key="help_btn", help="Help"):
            st.toast("Upload any document and ask anything!", icon="💡")
    with ic4:
        if st.button("🔄", use_container_width=True, key="refresh_btn", help="Refresh"):
            st.rerun()

    if st.session_state.show_settings:
        with st.expander("⚙️ Settings", expanded=False):
            st.caption("Models: Gemini 2.5 Flash · Pro (with tools)")
            st.caption("Search: Tavily Web Search API")
            st.caption("Memory: ChromaDB local vector store")
            st.caption("SDK: google-genai 2026")
            st.caption("Student OS v1.0")


# ══════════════════════════════════════════════════════════
#  PDF DOWNLOAD BANNER
# ══════════════════════════════════════════════════════════
if st.session_state.pdf_ready and st.session_state.pending_pdf and st.session_state.messages:
    c1, c2 = st.columns([3, 1])
    with c1:
        st.success("✅ **Your Practice Sheet is ready!**")
    with c2:
        st.download_button(
            label="📥 Download PDF",
            data=st.session_state.pending_pdf,
            file_name="StudentOS_Sheet.pdf",
            mime="application/pdf",
            use_container_width=True,
            key="pdf_persistent_btn",
        )
    st.divider()


# ══════════════════════════════════════════════════════════
#  CHAT DISPLAY
# ══════════════════════════════════════════════════════════
if not st.session_state.messages:
    st.markdown("""
    <div style='text-align:center; padding:5rem 0 2rem;'>
        <h1 style='font-size:3.5rem; margin:0;'>🎓 Student OS</h1>
        <p style='color:#888; font-size:1.2rem; margin-top:.5rem;'>
            Your Universal Research Agent
        </p>
        <p style='color:#aaa; font-size:.95rem;'>
            Ask anything · Upload any notes · Search the web · Watch YouTube
        </p>
    </div>
    """, unsafe_allow_html=True)
else:
    for msg in st.session_state.messages:
        icon = "🧑‍🎓" if msg["role"] == "user" else "🎓"
        with st.chat_message(msg["role"], avatar=icon):
            st.markdown(msg["content"])
            # Show tool badges if stored
            if msg.get("tools_used"):
                badges = []
                if msg.get("used_local"):   badges.append("📚 Notes")
                if msg.get("used_web"):     badges.append("🔍 Web")
                if msg.get("used_youtube"): badges.append("🎬 YouTube")
                if badges:
                    st.caption("Sources used: " + "  ·  ".join(badges))


# ══════════════════════════════════════════════════════════
#  VOICE PANEL
# ══════════════════════════════════════════════════════════
if st.session_state.show_voice:
    with st.container():
        st.markdown("#### 🎤 Voice Input")
        components.html("""
        <div style="font-family:sans-serif; padding:10px; text-align:center;">
            <button id="micBtn" onclick="toggleMic()" style="
                width:64px; height:64px; border-radius:50%;
                font-size:28px; border:2px solid #4a9eff;
                background:none; cursor:pointer; color:#4a9eff; transition:all 0.2s;">🎤</button>
            <p id="status" style="color:#888; font-size:13px; margin:10px 0 6px;">
                Click the mic and speak
            </p>
            <div id="output" style="min-height:36px; padding:8px 12px;
                background:rgba(255,255,255,0.06); border-radius:8px;
                font-size:15px; color:#ddd;"></div>
        </div>
        <script>
        let rec, going = false;
        function toggleMic() {
            if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
                document.getElementById('status').innerText = '❌ Use Chrome for voice support';
                return;
            }
            if (going) { rec.stop(); return; }
            rec = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
            rec.lang = 'en-US'; rec.interimResults = true;
            rec.onstart = () => {
                going = true;
                document.getElementById('micBtn').style.color = '#ff4444';
                document.getElementById('micBtn').style.borderColor = '#ff4444';
                document.getElementById('status').innerText = '🔴 Listening...';
            };
            rec.onresult = e => {
                let t = '';
                for (let i = e.resultIndex; i < e.results.length; i++)
                    t += e.results[i][0].transcript;
                document.getElementById('output').innerText = t;
            };
            rec.onend = () => {
                going = false;
                document.getElementById('micBtn').style.color = '#4a9eff';
                document.getElementById('micBtn').style.borderColor = '#4a9eff';
                document.getElementById('status').innerText =
                    document.getElementById('output').innerText.trim()
                    ? '✅ Done! Paste below.' : 'Nothing heard. Try again.';
            };
            rec.start();
        }
        </script>
        """, height=190)

        voice_typed = st.text_input(
            "Paste recognised text:",
            key="voice_text_input",
            placeholder="Copy from above and paste here...",
        )
        v1, v2 = st.columns(2)
        with v1:
            if st.button("✅ Send", use_container_width=True, key="send_voice"):
                if voice_typed.strip():
                    st.session_state.queued_msg = voice_typed.strip()
                    st.session_state.show_voice = False
                    st.rerun()
                else:
                    st.warning("Paste text first.")
        with v2:
            if st.button("✕ Cancel", use_container_width=True, key="cancel_voice"):
                st.session_state.show_voice = False
                st.rerun()
    st.divider()


# ══════════════════════════════════════════════════════════
#  MIC BUTTON
# ══════════════════════════════════════════════════════════
_mic_state = st.checkbox(
    "mic_toggle", value=st.session_state.show_voice,
    key="mic_checkbox", label_visibility="collapsed",
)
if _mic_state != st.session_state.show_voice:
    st.session_state.show_voice = _mic_state
    st.rerun()

components.html("""
<script>
(function injectMic() {
    const doc  = window.parent.document;
    const wrap = doc.querySelector('[data-testid="stChatInput"]');
    if (!wrap) { setTimeout(injectMic, 300); return; }
    if (doc.getElementById('ew-mic-btn')) return;
    const mic = doc.createElement('button');
    mic.id = 'ew-mic-btn'; mic.type = 'button'; mic.title = 'Voice input';
    mic.innerHTML = '&#x1F3A4;';
    mic.onclick = (e) => {
        e.preventDefault(); e.stopPropagation();
        const cb = doc.querySelector('input[type="checkbox"][aria-label="mic_toggle"]')
                || doc.querySelector('.stCheckbox input[type="checkbox"]');
        if (cb) { cb.click(); return; }
    };
    wrap.appendChild(mic);
    const textarea = wrap.querySelector('textarea');
    function update() {
        const hasText = textarea && textarea.value.trim().length > 0;
        mic.style.display = hasText ? 'none' : 'block';
        if (hasText) wrap.classList.add('has-text');
        else wrap.classList.remove('has-text');
    }
    if (textarea) {
        ['input','keyup','change'].forEach(ev => textarea.addEventListener(ev, update));
        textarea.addEventListener('keydown', e => {
            if (e.key === 'Enter' && !e.shiftKey) {
                setTimeout(update, 100); setTimeout(update, 400);
            }
        });
    }
    update(); setInterval(update, 500);
})();
</script>
""", height=0)


# ══════════════════════════════════════════════════════════
#  CHAT INPUT
# ══════════════════════════════════════════════════════════
typed_input = st.chat_input("Ask anything — any subject, any level…")

user_input = None
if typed_input:
    user_input = typed_input
elif st.session_state.queued_msg:
    user_input = st.session_state.queued_msg
    st.session_state.queued_msg = None


# ══════════════════════════════════════════════════════════
#  INPUT PIPELINE
# ══════════════════════════════════════════════════════════
if user_input:

    # 1. Show user message
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user", avatar="🧑‍🎓"):
        st.markdown(user_input)

    # 2. Smart PDF shortcut
    if ai_offered_pdf(st.session_state.messages) and user_said_yes_to_pdf(user_input):
        last_q = get_last_ai_questions(st.session_state.messages)
        if last_q:
            with st.chat_message("assistant", avatar="🎓"):
                st.markdown("Generating your PDF now… 🚀")
            st.session_state.messages.append({
                "role": "assistant", "content": "Generating your PDF now… 🚀"
            })
            build_pdf_and_show(last_q, "Student OS — Practice Sheet")
            st.stop()

    # 3. Run orchestrator with live status indicators
    orchestrator  = get_orchestrator()
    full_response = ""
    used_local    = False
    used_web      = False
    used_youtube  = False

    with st.chat_message("assistant", avatar="🎓"):
        placeholder = st.empty()
        streamed    = ""

        # ── Live status while tools run ────────────────────
        memory = get_memory()
        has_memory = memory and memory.count() > 0

        # Classify query to predict tool usage for status display
        from service import _classify_query, WEB_SIGNALS, YOUTUBE_SIGNALS
        classification = _classify_query(user_input)
        q_lower        = user_input.lower()
        will_search_web = (
            classification["needs_web"] or
            (not has_memory) or
            any(s in q_lower for s in WEB_SIGNALS)
        )
        will_search_yt = classification["needs_youtube"]

        # Show predictive status
        with st.status("🤔 Thinking…", expanded=False) as status_box:
            if has_memory:
                st.write("📚 Searching your notes…")
            if will_search_web:
                st.write("🔍 Searching the web…")
            if will_search_yt:
                st.write("🎬 Fetching video transcript…")

            # Run the orchestrator stream
            for key_idx in range(len(GEMINI_KEYS)):
                try:
                    for text_chunk in orchestrator.stream(user_input, key_index=key_idx):
                        streamed += text_chunk
                        placeholder.markdown(
                            ResponseFormatter.add_streaming_cursor(streamed)
                        )
                    break

                except Exception as e:
                    if "429" in str(e) and key_idx < len(GEMINI_KEYS) - 1:
                        st.write("🔄 Switching to backup key…")
                        streamed = ""
                        continue
                    else:
                        st.write(f"❌ Error: {e}")
                        break

            # Update status with actual tools used
            result = orchestrator.last_result
            if result:
                used_local   = result.used_local
                used_web     = result.used_web
                used_youtube = result.used_youtube

                label_parts = ["✅ Done"]
                if used_local:   label_parts.append("📚 Notes")
                if used_web:     label_parts.append("🔍 Web")
                if used_youtube: label_parts.append("🎬 YouTube")
                status_box.update(
                    label=f"{'  ·  '.join(label_parts)}",
                    state="complete",
                    expanded=False,
                )

        full_response = ResponseFormatter.clean(streamed).strip()
        placeholder.markdown(full_response)

    # 4. Save to session memory
    if full_response:
        msg_entry = {
            "role":         "assistant",
            "content":      full_response,
            "tools_used":   True,
            "used_local":   used_local,
            "used_web":     used_web,
            "used_youtube": used_youtube,
        }
        st.session_state.messages.append(msg_entry)
        st.session_state.last_pdf_query = user_input

    # 5. Auto PDF if explicitly requested
    if full_response and user_wants_pdf(user_input):
        build_pdf_and_show(full_response, "Student OS — Practice Sheet")

st.divider()
