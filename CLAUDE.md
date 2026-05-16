# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Commands

```powershell
# Build vector store (required before first use)
& ".venv\Scripts\python.exe" ingest.py

# Interactive CLI
& ".venv\Scripts\python.exe" main.py

# One-shot mode
& ".venv\Scripts\python.exe" main.py 考大学应该给贫困地区的学生加分

# With debug output
$env:DEBUG = "1"; & ".venv\Scripts\python.exe" main.py

# FastAPI SSE server
& ".venv\Scripts\python.exe" server.py

# Run tests with coverage
& ".venv\Scripts\python.exe" -m pytest tests/ --cov=nodes --cov=retriever_node --cov=state --cov-report=term-missing

# Lint
& ".venv\Scripts\python.exe" -m ruff check . --exclude .venv
```

## Architecture

A LangGraph pipeline that implements Socratic dialogue around **social fairness (社会公平)**. The user states an opinion; the system responds with a counter-question via **adversarial retrieval** — never an answer.

### Pipeline

```
START → Analyzer → Retriever (Adversarial) ──score≤threshold──→ Socratic_Ironist → END
                                            ──score>threshold──→ Web_Search ──→ Socratic_Ironist → END
                                            (falls back to Socratic_Ironist if TAVILY_API_KEY unset)
```

Pipeline assembled in [graph.py](graph.py) via `build_graph(llm, embeddings)`. Conditional routing is handled by `route_after_retriever()` based on ChromaDB cosine distance vs `SIMILARITY_THRESHOLD`.

### Node responsibilities

| Node | File | What it does |
|------|------|-------------|
| **Analyzer** | `nodes.py:make_analyzer()` | Deep philosophical analysis via LLM + `json.loads()`. Extracts 5 fields: `core_claim`, `underlying_assumption`, `matched_philosophy`, `opponent_philosophy`, `opponent_core_argument`. Identifies the user's philosophical school and its classic opponent. |
| **Retriever (Adversarial)** | `retriever_node.py:make_retrieve_contradiction()` | Step 1: LLM generates a **counter-factual query** (not the user's claim, but the opposite). Step 2: semantic search in ChromaDB for `type=counter_example` documents. Returns top-2 counter-examples with cosine distance scores. |
| **Web_Search** | `web_search_node.py:make_web_search()` | Dynamic knowledge flow. When ChromaDB retrieval quality is insufficient (distance > threshold), searches the web via Tavily API for counter-examples. Merges results with existing `rag_counter_example`. Gracefully degrades if Tavily is unavailable. |
| **Socratic_Ironist** | `nodes.py:make_socratic_ironist()` | LLM call. Generates one sharp, everyday-language counter-question that challenges the user's hidden premise. Uses feigned ignorance, pushes to extremes, and targets inconsistencies in definitions. |

### Data model ([state.py](state.py))

- `DialogueState` — TypedDict shared across nodes. Flow: `user_input` → `core_claim` / `underlying_assumption` / `matched_philosophy` / `opponent_philosophy` / `opponent_core_argument` → `rag_counter_example` / `rag_relevance_score` / `knowledge_source` → `socratic_question`.
- `AnalyzerOutput` — Pydantic model for structured output from the Analyzer (5 fields + `PhilosophyCategory` literal type).

### Philosophical corpus ([data/raw_texts.py](data/raw_texts.py))

6 documents (3 claims + 3 counter-examples) covering 分配正义 (Rawls), 程序正义 (Nozick), 功利主义 (Bentham/Mill). Each document has `type: claim|counter_example` and `philosophy` metadata. Vectorized and stored in `chroma_db/` via [ingest.py](ingest.py).

### LLM & Embedding config (`.env`)

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` / `OPENAI_API_BASE` / `OPENAI_MODEL_NAME` | Chat LLM (Analyzer + Ironist) |
| `EMBEDDING_API_KEY` / `EMBEDDING_API_BASE` / `EMBEDDING_MODEL_NAME` | Embedding for ChromaDB (falls back to OPENAI_*) |
| `TAVILY_API_KEY` | Tavily web search API key (optional; enables dynamic knowledge flow) |
| `SIMILARITY_THRESHOLD` | Cosine distance threshold for quality routing (default 0.5) |

### Server ([server.py](server.py))

FastAPI SSE streaming server at `http://localhost:8000`:
- `POST /api/v1/socratic/stream` — SSE stream with per-node status events (`status`, `node_start`, `node_end`, `token`, `done`, `error`)
- `GET /health` — health check

### Frontend ([frontend/](frontend/))

React 19 + TypeScript + Vite + Framer Motion + react-markdown SPA at `http://localhost:5173`.

| File | Purpose |
|------|---------|
| [`useSocraticStream.ts`](frontend/src/hooks/useSocraticStream.ts) | SSE stream hook — handles fetch, abort, 6 SSE event types, token accumulation |
| [`App.tsx`](frontend/src/App.tsx) | Layout: Sidebar + DialogueArea |
| [`Sidebar.tsx`](frontend/src/components/Sidebar.tsx) | Real-time node progress display with philosophy color tags |
| [`DialogueArea.tsx`](frontend/src/components/DialogueArea.tsx) | Input box + streaming markdown output + reset/cancel |
| [`types.ts`](frontend/src/types.ts) | `AgentState` interface mirroring `DialogueState`, node labels, color palette |

Commands: `cd frontend && npm run dev` (dev) / `npm run build` (production).

### Key design decisions

- **Adversarial retriever**: Instead of RAG on similar texts, the retriever first asks the LLM "what counter-argument would disprove this claim?" then searches for that. This generates sharper challenges.
- **Quality-aware routing**: ChromaDB returns cosine distance scores (lower = more similar). Score ≤ threshold → use directly. Score > threshold → route to Tavily web search for supplementary counter-examples. Falls back gracefully if Tavily is unconfigured.
- **Separate embedding provider**: DeepSeek doesn't support `/v1/embeddings`. Embedding API config is independent of the chat LLM.
- **ChromaDB filter**: Only `type=counter_example` documents are returned — claims are excluded from search results.
- **Analyzer JSON parsing**: Uses format instruction + `json.loads()` (not `response_format`) for broader API compatibility. Has markdown code-block stripping fallback.
- **Stateless turns**: No conversation history maintained between rounds.
- **Deep opponent analysis**: Analyzer identifies both the user's philosophical school AND its classic opponent with core argument — giving the Ironist precise attack surface.
