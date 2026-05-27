# Development Workflow

Use this workflow for reliable local development. Prefer the documented PowerShell commands in `CLAUDE.md` when working in Windows shells; in Git Bash, use equivalent forward-slash paths such as `./.venv/Scripts/python.exe -m pytest tests/`.

## 1. Start-of-session checks

1. Run a quick status check before editing: `git status --short`.
2. Confirm the Python venv and frontend dependencies exist before running app checks:
   - Python commands should use `.venv\Scripts\python.exe` from the repo root.
   - Frontend commands should run from `frontend/`.
3. Leave generated/cache directories alone unless explicitly cleaning them: `.venv/`, `chroma_db/`, `.pytest_cache/`, `.ruff_cache/`, `frontend/.vite/`, and `frontend/node_modules/`.

## 2. Backend change loop

1. For node/state/routing changes, add or update focused tests in `tests/` first.
2. Run the narrowest relevant pytest target, for example:
   - `& ".venv\Scripts\python.exe" -m pytest tests/test_nodes.py`
   - `& ".venv\Scripts\python.exe" -m pytest tests/test_memory.py`
3. Run the full backend suite before considering the change complete:
   - `& ".venv\Scripts\python.exe" -m pytest tests/`
4. Run coverage when behavior changes cross node boundaries:
   - `& ".venv\Scripts\python.exe" -m pytest tests/ --cov=nodes --cov=retriever_node --cov=state --cov=graph --cov=web_search_node --cov-report=term-missing`
5. Run lint after Python edits:
   - `& ".venv\Scripts\python.exe" -m ruff check . --exclude .venv`

## 3. Corpus and retrieval changes

1. If `data/raw_texts.py` changes, rebuild the vector store immediately:
   - `& ".venv\Scripts\python.exe" ingest.py`
2. After rebuilding, test a representative retrieval path with one-shot CLI mode and, when useful, debug mode:
   - `& ".venv\Scripts\python.exe" main.py 考大学应该给贫困地区的学生加分`
   - `$env:DEBUG = "1"; & ".venv\Scripts\python.exe" main.py`
3. Verify fallback behavior when `TAVILY_API_KEY` is absent or web search fails; the app should still route to `Socratic_Ironist`.

## 4. Frontend change loop

1. Run the backend and frontend together for UI work:
   - backend: `& ".venv\Scripts\python.exe" server.py`
   - frontend: `cd frontend && npm run dev`
2. Manually verify the golden SSE path in a browser:
   - Submit a Chinese social-fairness prompt.
   - Confirm sidebar node progress advances through Analyzer/Retriever/Web_Search or ambush routing.
   - Confirm streamed tokens accumulate into one Socratic counter-question.
   - Test abort/cancel, empty input, and backend error states.
3. Run frontend validation before finishing UI changes:
   - `cd frontend && npm run lint`
   - `cd frontend && npm run build`
4. Check responsive behavior at minimum desktop and narrow mobile widths; watch for overflow in `DialogueArea` and `Sidebar`.

## 5. Security and configuration checks

1. Never commit `.env` or real API keys. Required secrets are `OPENAI_*`, optional `EMBEDDING_*`, and optional `TAVILY_API_KEY`.
2. Validate user-facing input and API errors at server boundaries; do not leak raw provider errors to the frontend.
3. Keep Claude hooks project-local in `.claude/settings.json`; do not promote this repo's pytest/ruff hooks to global settings.
4. Hook health check after editing `.claude/settings.json`:
   - JSON must parse.
   - Each hook event entry must use `matcher` plus a `hooks` array.
   - PostToolUse Ruff hooks should skip non-Python files and out-of-repo paths via `.claude/hook_ruff.py`.

## 6. Pre-commit quality gate

Before committing, run the smallest set that covers the touched surfaces:

- Python-only: ruff + relevant pytest + full `pytest tests/`.
- Retrieval/corpus: `ingest.py` + retrieval smoke test + relevant pytest.
- Frontend-only: `npm run lint` + `npm run build` + browser smoke test.
- Full-stack/SSE: backend server + frontend dev server + browser SSE smoke test + backend tests + frontend build.

If any check fails, fix the underlying cause instead of bypassing hooks or skipping tests.

## 7. Automatic commit policy

After the relevant quality gate passes, commit the completed changes automatically unless the user explicitly says not to commit.

Use a concise conventional commit message with enough context to explain why the change exists:

```text
<type>: <short description>

<1-3 bullets or sentences describing the purpose, validation performed, and any operational notes>
```

Recommended types:

- `fix`: broken behavior, invalid config, failing checks.
- `feat`: user-visible capability.
- `docs`: documentation-only workflow or guidance updates.
- `test`: test-only changes.
- `chore`: tooling, hooks, dependencies, generated maintenance.

For mixed changes, choose the type that describes the highest-impact user outcome. For example, a hook schema repair plus workflow documentation should use `fix:` because the primary outcome is restoring valid Claude Code configuration.
