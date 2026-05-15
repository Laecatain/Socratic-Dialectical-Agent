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

# Run tests with coverage
& ".venv\Scripts\python.exe" -m pytest tests/ --cov=nodes --cov=retriever_node --cov=state --cov-report=term-missing
```

## Architecture

A LangGraph pipeline that implements Socratic dialogue around **social fairness (社会公平)**. The user states an opinion; the system responds with a counter-question via **adversarial retrieval** — never an answer.

### Pipeline

```
User Input → Analyzer → Retriever (Adversarial) → Socratic_Ironist → Terminal
```

Pipeline assembled in [graph.py](graph.py) via `build_graph(llm, embeddings)`.

### Node responsibilities

| Node | File | What it does |
|------|------|-------------|
| **Analyzer** | `nodes.py:make_analyzer()` | LLM call with JSON prompt + `json.loads()`. Extracts `core_claim`, `underlying_assumption`, and `matched_philosophy`. |
| **Retriever (Adversarial)** | `retriever_node.py:make_retrieve_contradiction()` | Step 1: LLM generates a **counter-factual query** (not the user's claim, but the opposite). Step 2: semantic search in ChromaDB for `type=counter_example` documents. Returns top-2 counter-examples. |
| **Socratic_Ironist** | `nodes.py:make_socratic_ironist()` | LLM call. Generates one sharp, everyday-language counter-question that challenges the user's hidden premise. |

### Data model ([state.py](state.py))

- `DialogueState` — TypedDict shared across nodes. Flow: `user_input` → `core_claim` / `underlying_assumption` / `matched_philosophy` → `rag_counter_example` → `socratic_question`.
- `AnalyzerOutput` — Pydantic model for structured output from the Analyzer.

### Philosophical corpus ([data/raw_texts.py](data/raw_texts.py))

6 documents (3 claims + 3 counter-examples) covering 分配正义 (Rawls), 程序正义 (Nozick), 功利主义 (Bentham/Mill). Each document has `type: claim|counter_example` and `philosophy` metadata. Vectorized and stored in `chroma_db/` via [ingest.py](ingest.py).

### LLM & Embedding config (`.env`)

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` / `OPENAI_API_BASE` / `OPENAI_MODEL_NAME` | Chat LLM (Analyzer + Ironist) |
| `EMBEDDING_API_KEY` / `EMBEDDING_API_BASE` / `EMBEDDING_MODEL_NAME` | Embedding for ChromaDB (falls back to OPENAI_*) |

### Key design decisions

- **Adversarial retriever**: Instead of RAG on similar texts, the retriever first asks the LLM "what counter-argument would disprove this claim?" then searches for that. This generates sharper challenges.
- **Separate embedding provider**: DeepSeek doesn't support `/v1/embeddings`. Embedding API config is independent of the chat LLM.
- **ChromaDB filter**: Only `type=counter_example` documents are returned — claims are excluded from search results.
- **Analyzer JSON parsing**: Uses format instruction + `json.loads()` (not `response_format`) for broader API compatibility. Has markdown code-block stripping fallback.
- **Stateless turns**: No conversation history maintained between rounds.
