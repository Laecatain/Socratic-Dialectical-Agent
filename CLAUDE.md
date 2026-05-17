# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```powershell
# Build vector store (required before first use — run after any corpus change)
& ".venv\Scripts\python.exe" ingest.py

# Interactive CLI
& ".venv\Scripts\python.exe" main.py

# One-shot mode (no REPL)
& ".venv\Scripts\python.exe" main.py 考大学应该给贫困地区的学生加分

# With debug output (shows intermediate Analyzer/Retriever results)
$env:DEBUG = "1"; & ".venv\Scripts\python.exe" main.py

# FastAPI SSE server (backend for the frontend SPA)
& ".venv\Scripts\python.exe" server.py

# Frontend dev server (Vite — run alongside server.py)
cd frontend && npm run dev

# Frontend production build
cd frontend && npm run build

# Run all tests
& ".venv\Scripts\python.exe" -m pytest tests/

# Run a single test file
& ".venv\Scripts\python.exe" -m pytest tests/test_nodes.py

# Run a single test by name
& ".venv\Scripts\python.exe" -m pytest tests/test_nodes.py -k "test_analyzer"

# Run tests with coverage
& ".venv\Scripts\python.exe" -m pytest tests/ --cov=nodes --cov=retriever_node --cov=state --cov-report=term-missing

# Lint
& ".venv\Scripts\python.exe" -m ruff check . --exclude .venv
```

## Architecture

A LangGraph pipeline with **multi-turn memory** that implements Socratic dialogue around **social fairness (社会公平)**. The system tracks each user's admitted premises across conversation turns via `MemorySaver` checkpointer, and detects logical self-contradiction to deliver targeted "ambush" counter-questions. Each turn receives a counter-question via **adversarial retrieval** — never an answer.

### Pipeline

```
START → Analyzer ──contradiction──→ Socratic_Ironist (ambush) → END
                 ──no contradiction→ Retriever (HyDE)
                                        ├─ score≥threshold → Socratic_Ironist → END
                                        └─ score<threshold → Web_Search → Socratic_Ironist → END
                                        (falls back to Socratic_Ironist if TAVILY_API_KEY unset)
```

Multi-turn state persistence via LangGraph `MemorySaver` checkpointer. Each session gets a `thread_id` — the graph restores `admitted_premises` from previous turns and the Analyzer cross-references them against the current input to detect contradictions.

Pipeline assembled in [graph.py](graph.py) via `build_graph(llm, embeddings)`. Conditional routing: (1) `route_after_analyzer()` — shortcut to Ironist when contradiction detected, else route to Retriever; (2) `route_after_retriever()` — ChromaDB similarity score vs `SIMILARITY_THRESHOLD` (default 0.5). Graph compiled with `MemorySaver` checkpointer.

### Node responsibilities

Every node is a **factory function** that returns a callable — closures capture the LLM/embeddings instance, so nodes have no mutable state:

| Node | Factory (file) | What it does |
|------|---------------|-------------|
| **Analyzer** | `make_analyzer(llm)` in [nodes.py](nodes.py) | LLM call with JSON format instruction → `json.loads()` (with markdown code-block stripping fallback). Extracts 5 base fields + cross-references current input against `admitted_premises` to detect logical contradictions. When contradiction found, sets `has_contradiction=True` and `target_premise_id`. |
| **Retriever** | `make_retrieve_contradiction(llm, embeddings)` in [retriever_node.py](retriever_node.py) | Two-step adversarial search (HyDE): (1) LLM generates a **counter-argument text**, (2) ChromaDB `similarity_search_with_score`, returns top-K with normalized similarity score. No hard metadata filter. |
| **Web_Search** | `make_web_search()` in [web_search_node.py](web_search_node.py) | Tavily API web search for counter-examples. Appends results to existing `rag_counter_example` (doesn't replace). Gracefully degrades on missing key, missing package, or API failure — returns `[FALLBACK]` markers. |
| **Socratic_Ironist** | `make_socratic_ironist(llm)` in [nodes.py](nodes.py) | **Dual-mode**: Normal mode generates one sharp counter-question (≤80 chars, everyday language, feigned ignorance). **Ambush mode** (when `has_contradiction=True`) uses the user's own historical premise against them — simultaneously references the past admission and current contradiction in one surgical反问. |

### Data model ([state.py](state.py))

- `DialogueState` — TypedDict shared across all nodes. Flow: `user_input` → Analyzer's 5 fields + contradiction detection → `rag_counter_example` / `rag_relevance_score` / `knowledge_source` → `socratic_question`. Plus `turn_count`. Multi-turn fields: `admitted_premises`, `has_contradiction`, `contradiction_details`, `target_premise_id`, `target_premise_statement`, `target_premise_turn`.
- `AnalyzerOutput` — Pydantic model with `PhilosophyCategory` literal type (8 philosophy schools + "未知").
- `AnalyzerMultiTurnOutput` — Extended output model with `extracted_new_premise`, `detected_contradiction`, `contradiction_analysis`, `conflicting_premise_id` for cross-turn auditing.
- `AdmittedPremise` — Pydantic model tracking each user-conceded premise: `premise_id`, `turn_index`, `statement`, `philosophical_alignment`, `is_active`.

### Vector store ([ingest.py](ingest.py) + [data/raw_texts.py](data/raw_texts.py))

6 documents (3 claims + 3 counter-examples) from Rawls, Nozick, Bentham/Mill. Embedded via the EMBEDDING model into ChromaDB (`chroma_db/`, cosine space). Each document tagged with `type: claim|counter_example` and `philosophy` — the Retriever filters to `counter_example` only.

**Must re-run `ingest.py` after editing `raw_texts.py`.**

### Server ([server.py](server.py))

FastAPI SSE streaming at `http://localhost:8000`. `POST /api/v1/socratic/stream` accepts `{"text": "..."}` and streams 6 event types (`status`, `node_start`, `node_end`, `token`, `done`, `error`) via LangGraph's `astream_events()`. Has per-request disconnect detection via `request.is_disconnected()`.

### Frontend ([frontend/](frontend/))

React 19 + TypeScript + Vite + Framer Motion + react-markdown SPA at `http://localhost:5173`. The core hook [`useSocraticStream.ts`](frontend/src/hooks/useSocraticStream.ts) manages the full SSE lifecycle (fetch, stream parsing, abort, token accumulation). `Sidebar.tsx` shows per-node progress with philosophy color tags; `DialogueArea.tsx` handles input + streaming markdown output.

### LLM & Embedding config (`.env`)

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` / `OPENAI_API_BASE` / `OPENAI_MODEL_NAME` | Chat LLM (Analyzer + Ironist + counter-query generation) |
| `EMBEDDING_API_KEY` / `EMBEDDING_API_BASE` / `EMBEDDING_MODEL_NAME` | Embedding model for ChromaDB (falls back to OPENAI_* if unset) |
| `TAVILY_API_KEY` | Optional. Enables Web_Search node when ChromaDB quality is insufficient |
| `SIMILARITY_THRESHOLD` | Cosine distance threshold for quality routing (default 0.5, range 0-2) |

Chat and Embedding providers can be different — DeepSeek doesn't support `/v1/embeddings`, so `EMBEDDING_*` (e.g. DashScope) is configured independently.

### Testing strategy

4 test files, all using `RunnableLambda` as a **fake LLM** instead of mocking — the chain `prompt | fake_llm` still exercises LangChain's pipe operator and prompt templates, returning hardcoded responses:

| File | What it tests | Approach |
|------|--------------|----------|
| `test_nodes.py` | Analyzer JSON parsing (including markdown-stripping), Ironist template variable injection | RunnableLambda fake LLM |
| `test_retriever.py` | HyDE counter-argument factory, empty-claim guard, prompt template construction | Mock embeddings (no ChromaDB) |
| `test_state.py` | AnalyzerOutput + AnalyzerMultiTurnOutput Pydantic validation, PhilosophyCategory literals | Pure unit test |
| `test_memory.py` | AdmittedPremise model, multi-turn contradiction detection, Ironist ambush mode, 3-turn end-to-end ambush simulation | RunnableLambda fake LLM with dynamic response functions per turn |

Coverage gap: `retriever_node.py` at ~42% — the ChromaDB integration path needs a real vector store and embedding API.

### Key design decisions

- **Multi-turn memory via checkpointer**: `MemorySaver` persists state across turns via `thread_id` in config. Each session accumulates `admitted_premises` — the Analyzer cross-references new input against historical premises to detect contradictions.
- **Contradiction-first routing**: When the Analyzer detects self-contradiction, the pipeline shortcuts directly to the Ironist (ambush mode), skipping RAG entirely. The ambush template references both the historical premise and current claim.
- **Adversarial retrieval (HyDE)**: Search for "what would disprove the user's claim" — not similar texts. The LLM generates a hypothetical counter-argument before hitting ChromaDB.
- **Quality-aware routing**: ChromaDB similarity scores determine whether to use local results or supplement with Tavily web search. Falls back gracefully.
- **Opponent analysis**: Analyzer identifies both the user's philosophical school AND its classic opponent with core argument — gives the Ironist a precise attack vector, not a generic counter-question.
- **Factory functions over classes**: Nodes are closures (`make_*`), not objects. No mutable node state — all state in `DialogueState`.
- **`json.loads()` over `response_format`**: Broader API compatibility (DeepSeek, open-source models don't support structured output). Has markdown stripping fallback.
