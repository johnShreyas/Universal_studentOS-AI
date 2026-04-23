# Universal_studentOS-AI

I have built my first AI tool using python. I designed an AI tool for students to increase their productivity. An autonomous, hybrid AI system designed for multi-disciplinary research and tutoring. 
Built with Python, Streamlit, and a Local-Cloud Hybrid Architecture.

## 🚀 Core Features
- **Hybrid RAG Logic**: Uses local Ollama (Nomic-Embed) for document memory to bypass API limits and ensure data privacy.
- **Autonomous Orchestration**: Intelligent routing between local models (Qwen 2.5) and cloud models (Gemini 1.5 Flash/Pro).
- **Rate-Limit Resilience**: Implements exponential backoff and automated key rotation to maintain 100% uptime.

## 🏛️ Architecture
1. **Frontend**: Streamlit UI with integrated voice-to-text.
2. **Brain**: Custom Orchestrator (`service.py`) managing tool calls.
3. **Memory**: Local ChromaDB instance for permanent document storage.


NOTE : NOT FULLY BUILT 
