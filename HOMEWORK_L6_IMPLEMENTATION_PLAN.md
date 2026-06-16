# Implementation Plan — Multi-Agent Orchestration with LangGraph (Homework, Lessons 5–6)

> **Audience:** another Claude instance picking this up cold. This document is self-contained — read it fully before writing code, then read the existing files listed in §3. The homework is to **fill in the blanks** (11 stubbed functions = 9 graph nodes + 2 tools) in the existing `ai-orchestrator/` scaffold; you are *not* building a new project.

---

## 0. Working agreement & context discipline (read first)

**Execution mode:** You (the implementing AI) **write the code; the user reviews.** Implement **one step at a time** — a *step is a single stubbed function*, not a whole phase. After each step, run nothing further: pause, explain what you did and why, and hand the diff to the user for review before starting the next step. Do **not** batch steps unprompted (this is the "headless chicken" failure the user explicitly called out). Answering a question the user asked is **not** a go-ahead — the turn returns to the user.

**Always maintain a step-progress task list (TaskCreate/TaskUpdate)** so the user can follow along: at the start of each phase, create one task per step of that phase; mark a task `in_progress` when you begin it and `completed` when the user has accepted it. This is the visible progress tracker — keep it current.

**After every completed phase, update this plan to mark that phase `✅ DONE`** (on its `### Phase N` heading in §8). Do this as the final action of the phase so the plan always reflects which phases are finished.

**Every smoke test must be reported as an end-to-end trace, not just a pass/fail.** After running a smoke test, present to the user: (1) an **execution-flow map** — the command, then the chain of files/methods the data passes through in execution order (e.g. `script → agent.run → graph → node_X → prompt/LLM → DB → back to script`), as a compact diagram, **without pasting code bodies** (the code is in the codebase — reference files/methods by name only); (2) the **actual input data** that flowed through (the rendered prompt sent to the LLM, the generated SQL, query params) and the **actual output data** (returned rows/DataFrame, final state fields like `status`/`retry_count`); (3) a table mapping each console line to the file/method that emitted it. Keep it visual and concise — the goal is to *see* the pipeline working with real data, not to re-read source.

**This is teaching mode.** The deliverable is the user's *understanding* of LangGraph multi-agent orchestration, not fast code. Before each step: say what the node does, why, and how it fits the graph. After: show the output and interpret it. Define new LangGraph terms the first time they appear (state, node, reducer, conditional edge, supervisor).

**Context discipline — treat this as seriously as the code:**
- **Do NOT read the heavy source artifacts.** Never open `lesson5.pdf`, `lesson6.pdf`, `homework lesson 6.pdf`, or `code-snippets lesson 5/`. They are megabytes of slide images and **buggy** reference snippets — **this plan already distilled everything you need**, including the snippet bugs to avoid (§9). Reading them burns context for zero gain.
- **Read only:** this plan → the specific existing files listed in §3 → code already on disk from earlier steps.
- **Push repo exploration into subagents** (Explore/Task) so file dumps stay out of the main thread — only the conclusion returns.

**This plan is the single source of truth.** If a step forces a deviation (e.g. a prompt expects a variable not listed here), **edit this file** to record it before moving on. State lives in this document, not in any one conversation.

---

## 1. Goal

The homework PDF (`homework lesson 6.pdf`) is two slides:

- **L5 — Data Reader Agent with LangGraph:** typed state (Pydantic/TypedDict), nodes, conditional edges, a retry/fallback loop. "Demo: agent answers from RAG, CSV, or SQL."
- **L6 — Multi-Agent Orchestration:** extend the L5 agent into a multi-agent system with a **Supervisor** that chooses workers, **shared state** with results aggregation, an **Analyst** that pre/postprocesses, and **error handling** (retry/fallback).

The `ai-orchestrator/` repo is the **concrete realization** of those two abstract slides. It already wires four LangGraph graphs; the homework is to **fill in 11 stubbed functions (9 graph nodes + 2 tools)** so the graphs actually work. Mapping (see §6 for detail):

| Homework concept | Realized in this repo as |
|---|---|
| L5 single agent: state → nodes → conditional edges → retry/fallback | **`NL2SQLAgent`** (`generate_sql → validate → execute`, with a `handle_error` retry loop) |
| L5 retrieval source + L6 supervisor-over-one-worker | **`Orchestrator`** (supervisor) driving **`RAGAgent`** (worker) in an evaluate → refine → answer loop |
| L6 supervisor choosing/wrapping workers + analyst pre/postprocess | **`AnalystAgent`** (supervisor): `make_plan` (preprocess/plan) → `execute_step` (calls NL2SQL workers + tools) → `synthesize` (postprocess/format) |
| L6 worker tools | **`join_data` / `filter_data`** in the vendored `skillab` tool registry |

**Acceptance demo:** `python src/main.py` runs `test_orchestrator()` (a document question answered from RAG, with the refine loop visible) and `test_analyst()` (a multi-step data question: query one/two tables → join/filter → synthesized answer).

---

## 2. Locked decisions (do not relitigate)

| Decision | Choice | Why |
|---|---|---|
| Where code lives | **Fill blanks inside `ai-orchestrator/`** — do not create new modules | Homework is "fill in the blanks"; the scaffold, graphs, and routing already exist. |
| Infra | **`ai-orchestrator/`'s OWN Docker stack** — `pgvector/pgvector:pg16`, host **port 5434**, db/user `demo`, password `demo123`, db name `rag_demo`. Run `docker compose up -d` from `ai-orchestrator/`. | **This is NOT the ai-engineer-lab stack.** See §2a. |
| LLM provider | **External provider via `skillab.get_llm()`**, selected by `.env` (`LLM_PROVIDER=openai\|gemini\|ollama`). **No litellm proxy.** | The agents default `llm = llm or get_llm()`; you don't construct LLMs — just call `self.llm.generate_sync(...)`. |
| `skillab-py` is a real dependency | **Installed editable: `pip install -e skillab-py`.** Editing `skillab/tools/implementations.py` *is* part of the homework. | It's vendored into this repo, not a black box. |
| State type | **Pydantic `BaseModel`** (already defined in `state.py`) — attribute access in nodes, return partial dicts. | Matches the scaffold; do not switch to TypedDict. |
| Reducers | **Accumulation is done manually** in `node_execute_step` (`state.step_results + [result]`), not via `Annotated[..., add]`. | The homework slide mentions reducers; this repo realizes the same aggregation imperatively. Note it when explaining, but **do not add `Annotated` reducers** — it would fight the existing graph. |
| Don't touch | `ai-engineer-lab/` and its `skillab-postgres` (5432) stack | Different project, different DB. Unrelated to this homework. |

### 2a. Infra is separate from ai-engineer-lab (verified)

| | `ai-orchestrator/` (this homework) | `ai-engineer-lab/` |
|---|---|---|
| Postgres image | `pgvector/pgvector:pg16` | `pgvector/pgvector:pg16` |
| Host port | **5434** | 5432 |
| DB / user / pass | `rag_demo` / `demo` / `demo123` | `skillab` / `skillab` / `skillab_dev` |
| LLM gateway | external provider (OpenAI/Gemini/Ollama) | local litellm + ollama (`skillab-litellm`, `skillab-ollama`) |
| `DATABASE_URL` | `postgresql://demo:demo123@localhost:5434/rag_demo` | `postgresql://skillab:skillab_dev@localhost:5432/skillab` |

**They share nothing** — no container, DB, credentials, port, or LLM gateway. The two stacks can run side by side (5432 vs 5434).

**The orchestrator publishes on host port 5434** (`docker-compose.yaml` `"5434:5432"`, `.env` `DATABASE_URL=...localhost:5434/rag_demo`); the container's internal port is still 5432. After `docker compose up -d`, confirm the container answering on **5434** is the `pgvector/pgvector:pg16` one.

---

## 3. Read these existing files first (then honor their contracts)

The repo lives at `/Users/vali/Work/AI/AI Engineer/ai-orchestrator/`.

- `README.md` — setup + run commands (summarized in §8 Phase 0).
- `src/state.py` — **all state schemas** (Pydantic `BaseModel`). The contracts you must satisfy. Key fields per state are in §6. Note `RAGAgentState.current_query` / `current_threshold` are **properties** (use them, don't recompute).
- `src/rag_agent.py` — `RAGAgent`. `node_search` is **COMPLETE** — read it as the canonical example of a finished node (how it builds `RAGSearchResult`, calls `RAGService.search`, computes scores). `node_refine` is **STUB** (your work).
- `src/orchestrator.py` — `Orchestrator` (supervisor over `RAGAgent`). `node_call_rag` and `_should_continue` are **COMPLETE**. `node_evaluate`, `node_answer` are **STUBS**. The stub docstrings contain step-by-step recipes — they are accurate; follow them.
- `src/nl2sql_agent.py` — `NL2SQLAgent`. `node_get_context` and all routing (`_route_after_*`) are **COMPLETE**. `node_generate_sql`, `node_validate_sql`, `node_execute_sql`, `node_handle_error` are **STUBS**.
- `src/analyst_agent.py` — `AnalystAgent` (supervisor). `node_execute_step`, `_execute_query`, `_execute_tool`, routing are **COMPLETE** — read them to see how a step's result lands in `state.slices[step.id]` and how NL2SQL workers + tools are invoked. `node_make_plan`, `node_synthesize` are **STUBS**.
- `src/database.py` — `transaction()` context manager (`with transaction() as db: ...`), `get_session()`, `DATABASE_URL`. Use `transaction()` inside `node_execute_sql`.
- `src/rag_service.py` — `RAGService(db).search(query, top_k, threshold) -> list[(chunk, score)]`. Used only by the COMPLETE `node_search`; you don't call it directly.
- `src/main.py` — `test_orchestrator()`, `test_analyst()` entry points (the acceptance demos). **Heads-up:** in `__main__` only `test_orchestrator()` is active; `test_analyst()` is commented out (`# test_analyst()  # uncomment după ce ai schema JSON`). You must uncomment it to run the Phase 4 demo. Note also `app.invoke(...)` here is accessed as a **dict** (`result['status']`, `result['answer']`) — see pitfall #9 about return-type access.
- `skillab-py/src/skillab/tools/implementations.py` — `join_data`, `filter_data` are **STUBS** (the homework's only edits outside `src/`).
- `skillab-py/src/skillab/tools/params.py` — `JoinDataParams` (`input_dfs, left_key, right_key, how`), `FilterDataParams` (`input_dfs, column, operator, value`). The tool signatures.
- `prompts/*.yaml` — the 7 prompt templates. Their Jinja variables are listed in §7; **pass every variable.** The registry uses plain Jinja2 (not `StrictUndefined`), so a missing **scalar** used as `{{ var }}` renders blank (a subtly wrong prompt, not an error) — **but** a missing var used in a loop/attribute access (`{% for k, v in columns.items() %}`, `{{ col_info.type }}`) raises `UndefinedError`. The `nl2sql_*` and `analyst_plan` templates iterate `columns`/`business_rules`/`tables` with `.items()`/`for`, so those dict/list vars must **always** be passed (use `{}`/`[]` if you have no data — never omit them).

There are **no new files to create** for the core homework (smoke scripts in §4 are the only additions).

---

## 4. Hard conventions (from `~/.claude/CLAUDE.md` and the scaffold's style)

1. **No 1–2 letter variable names.** `tool_call`, not `tc`; `dataframe` or `result_df`, not `df` where avoidable. (The stubs' commented hints use `df`/`col` — when you implement, prefer clearer names, but match the existing finished nodes' style where they already use a convention.)
2. **Avoid explanatory comments.** Prefer clear names and small helpers. The stub bodies have `# TODO` comments — replace them with code, don't leave them.
3. **Present ideas before doing them.** No unsolicited renames/refactors of the completed nodes, routing, or graph wiring. Touch only the stubbed bodies (and the two tool functions).
4. **Plan-first, one step at a time, smoke-test each phase.** Per §0.
5. **Match surrounding style:** Pydantic-state attribute access, `self.llm.generate_sync([{...}])`, `self.prompts.render(name, **vars)`, return a partial `dict`. Mirror the COMPLETE `node_search` (RAG) and `node_execute_step` (Analyst) as reference.
6. **Smoke tests are versioned `.py` files under `scripts/`**, named for what they exercise (`scripts/smoke_nl2sql.py`, not `smoke_phase1.py`), run via `python scripts/<name>.py`. `src/main.py`'s `test_*` functions already cover the integration demos — reuse them where they fit.

---

## 5. Repo map (✅ = complete, 🔲 = blank to fill)

```
ai-orchestrator/
├── docker-compose.yaml        # pgvector on 5434, db rag_demo (own stack)
├── .env.example               # DATABASE_URL + LLM_PROVIDER (copy → .env)
├── alembic/versions/          # 001 document_chunks (pgvector), 002 achizitii_directe, 003 anunturi_initiere
├── data/
│   ├── rag_demo.dump          # pg_restore data dump (chunks + tables)
│   └── nl2sql_agent/          # schema_*.json + business_*.json per table (the SQL "context")
├── scripts/                   # seed_chunks.py, seed_tables.py, clear_tables.py (+ your smoke_*.py)
├── prompts/                   # 7 Jinja YAML templates (§7)
├── src/
│   ├── state.py               # ✅ all Pydantic state schemas
│   ├── database.py            # ✅ transaction(), DATABASE_URL
│   ├── models.py              # ✅ ORM: DocumentChunk, AchizitieDirecta, AnuntInitiere
│   ├── repositories.py        # ✅ repos incl. vector similarity search
│   ├── rag_service.py         # ✅ RAGService.search()
│   ├── rag_agent.py           # node_search ✅ | 🔲 node_refine
│   ├── orchestrator.py        # node_call_rag ✅, routing ✅ | 🔲 node_evaluate, 🔲 node_answer
│   ├── nl2sql_agent.py        # node_get_context ✅, routing ✅ | 🔲 node_generate_sql, node_validate_sql, node_execute_sql, node_handle_error
│   ├── analyst_agent.py       # node_execute_step ✅, routing ✅ | 🔲 node_make_plan, 🔲 node_synthesize
│   └── main.py                # ✅ test_orchestrator(), test_analyst()
└── skillab-py/                # vendored lib, installed `pip install -e skillab-py`
    └── src/skillab/tools/implementations.py   # 🔲 join_data, 🔲 filter_data
```

**11 blanks total:** 1 (RAG) + 2 (Orchestrator) + 4 (NL2SQL) + 2 (Analyst) + 2 (tools) = 11 functions across 5 files. (9 graph nodes — RAG 1, Orch 2, NL2SQL 4, Analyst 2 — plus 2 tools.)

---

## 6. State schemas & the homework mapping (the contracts)

Nodes receive the state **object** (attribute access: `state.question`) and return a **partial dict**; LangGraph merges it (last-write-wins — these Pydantic states define **no reducers**, so a returned key replaces the field). Accumulation, where needed, is explicit in completed code.

- **`RAGAgentState`** — `query`, `feedback: OrchestratorFeedback|None`, `refined: RefinedQuery|None`, `result: RAGSearchResult|None`. Properties: `current_query`, `current_threshold`. `node_refine` returns `{"refined": RefinedQuery(...)}`. **Note:** `result` is `None` whenever `node_refine` runs — each orchestrator iteration starts a fresh `RAGAgentState` and `refine` precedes `search` (see Phase 2 step 3 / pitfall #14). Don't read `state.result.*` in `refine` without a `None` guard.
- **`OrchestratorState`** — `query`, `rag_result: RAGSearchResult|None`, `feedback: OrchestratorFeedback|None`, `iteration`, `answer`, `status`. `node_evaluate` → `{"feedback": ...}`; `node_answer` → `{"answer": ..., "status": ...}`.
- **`OrchestratorFeedback`** — `can_answer: bool`, `missing_info`, `wrong_context`, `suggestion`. This is the message the supervisor passes back to the RAG worker (L6 message-passing).
- **`RAGSearchResult`** — `query_used`, `results: list[SearchResultItem]`, `max_score`, `avg_score`. `SearchResultItem`: `content`, `summary`, `file_name`, `score`.
- **`NL2SQLState`** — `question`, `table_name`, `schema_context: dict`, `sql_query`, `is_valid`, `validation_error`, `result: pd.DataFrame`, `execution_error`, `retry_count`, `max_retries`, `status`.
- **`AnalystState`** — `question`, `reasoning`, `plan: list[QueryStep|ToolStep]`, `current_step`, `slices: dict[str, pd.DataFrame]`, `step_results: list[StepResult]`, `answer`, `status`. `QueryStep`(`id, action="query", table, sub_question`); `ToolStep`(`id, action="tool", tool_name, input_steps, params`).

**How this realizes L5/L6:** `NL2SQLState`'s `retry_count/max_retries` + the `handle_error→generate_sql` loop **is** the L5 retry/fallback. `OrchestratorState.feedback` flowing back into `RAGAgent.run(query, feedback)` **is** L6 supervisor↔worker message passing. `AnalystState.slices` accumulating per-step DataFrames, with `make_plan` (preprocess/intent) and `synthesize` (postprocess/format), **is** L6 analyst pre/postprocess + shared state.

---

## 7. Shared idioms (use these verbatim)

**LLM call** — returns a `str`:
```python
response = self.llm.generate_sync([{"role": "user", "content": prompt}])
```

**Prompt render** — returns a `str`; pass **every** variable the template uses (plain Jinja2, no StrictUndefined → missing vars silently blank):
```python
prompt = self.prompts.render("template_name", var1=..., var2=...)
```

**Extract JSON from a fenced ```json block** (no helper exists in the repo — write it inline):
```python
import re, json
match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
json_str = match.group(1) if match else response
feedback = OrchestratorFeedback.model_validate_json(json_str)   # Pydantic parse+validate
```

**DB query inside a node** (`node_execute_sql`):
```python
from sqlalchemy import text
from database import transaction
with transaction() as db:
    result = db.execute(text(state.sql_query))
    dataframe = pd.DataFrame(result.mappings().all())
```

**Graph wiring is already done.** Two `add_conditional_edges` forms appear: a dict mapping (`orchestrator.py`) and a **bare list of destination node names** (`nl2sql_agent.py`, `analyst_agent.py`) where the routing function returns the destination name directly (including `END`). You don't edit wiring — just know the routing functions (`_route_*`) read fields your nodes set (`is_valid`, `execution_error`, `retry_count`, `feedback.can_answer`, `plan`, `current_step`).

**Prompt template variables (pass all of these):**

| Template | Variables |
|---|---|
| `rag_evaluate` | `query`, `context`, `max_score`, `avg_score` |
| `rag_answer` | `query`, `context` |
| `rag_refine` | `original_query`, `current_query`, `found_summary`, `max_score`, `avg_score`, `current_threshold`, **`can_answer`, `missing_info`, `suggestion`** (the feedback fields **flattened** — the template reads `{{ can_answer }}`/`{{ missing_info }}`/`{{ suggestion }}`, NOT a `feedback` object; passing `feedback=...` leaves all three blank) |
| `nl2sql_generate` | `table_name`, `table_description`, `columns` (dict), `business_rules` (dict), `question` |
| `nl2sql_error` | `table_name`, `question`, `failed_sql`, `error_message`, `columns` (dict) |
| `analyst_plan` | `tables` (list of `{name, description, columns}`), `tools_catalog`, `question`, `history` (optional) |
| `analyst_synthesize` | `question`, `reasoning`, `results` (list of StepResult), `final_data` (optional string) |

> **Where these vars come from (verified against the data files):** `NL2SQLAgent.__init__` loads **only** `schema_path` into `self.schema`, which the completed `node_get_context` surfaces as `state.schema_context`. The schema JSON has keys `table_name`, `description`, `columns` (`{col: {type, description}}`) — and **nothing else**. So:
> - `table_name` → `state.table_name` (or `schema_context["table_name"]`)
> - `table_description` → `schema_context["description"]`
> - `columns` → `schema_context["columns"]`
> - `business_rules` → **NOT in the schema JSON.** The rules live in `data/nl2sql_agent/business_*.json` (shape `{table_name, rules}`), which the agent **never loads**. So either pass `business_rules={}` (the template's rules section renders empty — acceptable for the homework) **or**, if you want real rules, load `business_*.json` yourself inside `node_generate_sql`/`node_get_context`. Do **not** omit the variable — the template iterates it with `.items()` and would raise `UndefinedError`.
>
> For `nl2sql_error`, `error_message` is the failure being corrected: set `error_message = state.execution_error or state.validation_error` (the error node is reachable from both a validation failure and an execution failure — see §8 Phase 1), and `failed_sql = state.sql_query`.

---

## 8. Phased tasks (each phase ends in a smoke test; each node is its own step)

### Phase 0 — Infra & data (no code; verify the environment) — ✅ DONE
1. **Port** (§2a): orchestrator publishes on host port **5434**. Ensure the container on host port 5434 is the orchestrator's `pgvector/pgvector:pg16`.
2. `python -m venv` / use existing venv; `pip install -r requirements.txt`; **`pip install -e skillab-py`** (editable, so your tool edits take effect).
3. `cp .env.example .env`; set `LLM_PROVIDER` + the matching API key (Gemini or OpenAI recommended over local Ollama for reliable SQL/JSON generation).
4. `docker compose up -d` (from `ai-orchestrator/`); `alembic upgrade head`; restore data:
   `docker exec -i <orchestrator-postgres-container> pg_restore -U demo -d rag_demo --data-only < data/rag_demo.dump`
   (if the dump restore is flaky, `python scripts/seed_chunks.py` + `python scripts/seed_tables.py` are the fallback path).
- **Smoke:** a SQLAlchemy connection to `DATABASE_URL` succeeds; `SELECT count(*)` on `document_chunks`, `achizitii_directe`, `anunturi_initiere` returns non-zero (README expects ~135 chunks, ~694k contracts, ~8k notices); `SELECT '...'::vector` works (pgvector live).

### Phase 1 — NL2SQL Agent (L5 core: state → nodes → conditional edges → retry/fallback) — ✅ DONE

> **⚠️ Read this before writing — the retry loop's correction logic lives in `generate_sql`, NOT `handle_error`.** The graph wiring is locked: `handle_error → generate_sql → validate_sql → execute_sql`. That means **`generate_sql` is the node that actually produces the SQL that gets validated and executed on every pass, including retries.** If you (as the stub docstring loosely suggests) put the "render `nl2sql_error` and return corrected SQL" logic in `handle_error`, that corrected SQL is immediately **discarded** by the very next node — `generate_sql` regenerates from scratch — and the agent re-emits the same failing query until `max_retries`. So: **`generate_sql` is error-aware** (it renders `nl2sql_error` whenever a prior error is present), and **`handle_error` is just the retry counter / terminal-failure decision.**
>
> State hygiene that makes this work (no reducers — a returned key only replaces *that* key, stale values persist otherwise): `generate_sql` **clears both error fields** when it regenerates, and `execute_sql` **clears `execution_error` on success**. Combined with `validate_sql` always returning a fresh `validation_error`, this guarantees that at the moment `handle_error` runs, **exactly one** of `execution_error` / `validation_error` is non-empty — so `state.execution_error or state.validation_error` always names the real, current failure.

Fill the four stubs in `src/nl2sql_agent.py`, one step at a time:

1. **`node_generate_sql`** (error-aware — the brain of the retry loop):
   - **First pass** (`not state.execution_error and not state.validation_error`): render `nl2sql_generate` (vars from §7, sourced from `state.schema_context`; remember `business_rules={}` if you don't load `business_*.json`), `generate_sync`, strip ` ```sql ` fences. Return `{"sql_query": cleaned}`.
   - **Retry pass** (a prior error is present): `error_message = state.execution_error or state.validation_error`; render `nl2sql_error` with `table_name`, `question`, `failed_sql=state.sql_query`, `error_message`, `columns`; `generate_sync`; strip fences. Return `{"sql_query": cleaned, "execution_error": "", "validation_error": ""}` — **clearing both errors is required** so the next `validate`/`execute` writes a clean, current error if it fails again.
2. **`node_validate_sql`** → reject injection/DDL: parse with `sqlparse`, confirm the statement is a single `SELECT` (no `DROP/DELETE/UPDATE/INSERT/ALTER/;`-chained statements). Return `{"is_valid": bool, "validation_error": str}` (empty string when valid). (`_route_after_validate` sends `True`→execute, `False`→handle_error.)
3. **`node_execute_sql`** → run via `transaction()` + `text(...)`, `pd.DataFrame(result.mappings().all())`; **success → `{"result": df, "status": "success", "execution_error": ""}`** (the explicit `"execution_error": ""` is **mandatory** — `_route_after_execute` routes on a truthy `execution_error`, so a stale value from a prior failed attempt would wrongly bounce a *successful* retry back to `handle_error`); exception → `{"execution_error": str(error), "status": "failed"}`.
4. **`node_handle_error`** (retry counter only — do **not** generate SQL or clear errors here; `generate_sql` consumes the error on the next pass): `new_count = state.retry_count + 1`; if `new_count >= state.max_retries` return `{"retry_count": new_count, "status": "failed"}`; else return `{"retry_count": new_count}`. (`_route_after_error` loops back to `generate_sql` while `retry_count < max_retries`, where the error-aware regeneration happens.)
- **Smoke (`scripts/smoke_nl2sql.py`):** instantiate `NL2SQLAgent(table_name="achizitii_directe", schema_path="data/nl2sql_agent/schema_achizitii_directe.json")`; `run("...")` on a real question returns `status="success"` and a non-empty DataFrame. Bonus: a question that produces bad SQL shows the `handle_error → generate_sql` retry in the logs **with the second `[GENERATE]` rendering `nl2sql_error`** (different SQL the second time), then recovers or ends `failed` after `max_retries`. If the retry re-emits *identical* SQL, your correction logic is in the wrong node (see the warning above).

### Phase 2 — RAG Agent + Orchestrator (L5 retry/refine + L6 supervisor-over-worker)
Implement in dependency order so each step is observable:
1. **`orchestrator.node_answer`** (`src/orchestrator.py`) — build `context` from `state.rag_result.results`, render `rag_answer`, `generate_sync`; `status = "success"` if `state.feedback and state.feedback.can_answer`, `"partial"` if answered without `can_answer`, `"failed"` if no results. Return `{"answer": ..., "status": ...}`. (Lets you get a baseline answer before the loop logic exists.)
2. **`orchestrator.node_evaluate`** — build `context`, render `rag_evaluate` (with `max_score`/`avg_score`), `generate_sync`, extract JSON, `OrchestratorFeedback.model_validate_json(...)`, return `{"feedback": feedback}`. This drives `_should_continue` (loop back to `call_rag` while `not can_answer` and `iteration < max_iterations`, else `answer`).
3. **`rag_agent.node_refine`** (`src/rag_agent.py`) — if `state.feedback is None` return `{"refined": RefinedQuery(query=state.query)}` (first pass, unchanged). Else render `rag_refine` and return `{"refined": RefinedQuery.model_validate_json(...)}`. **Two traps here (both verified against the wiring):**
   - **`state.result` is `None` on every refine pass — guard it or you crash.** The orchestrator calls `self.rag.run(query, feedback)`, which builds a **fresh** `RAGAgentState(query=..., feedback=...)` each time — `refined` and `result` start `None`, and `refine` runs *before* `search`. So the previous search's chunks are **not** threaded back in. Build `found_summary = "..." if state.result else ""` (don't do `state.result.results` unguarded → `AttributeError`), and default `max_score`/`avg_score` to `0.0` when `state.result is None`. Consequence: `found_summary` is effectively always empty and `current_query` always equals `original_query` — **the real refinement signal is the `feedback` fields, not the prior results.** That's the scaffold's design; don't try to "fix" it by editing the orchestrator wiring.
   - **Pass the feedback fields flattened** (`can_answer=state.feedback.can_answer`, `missing_info=...`, `suggestion=...`), not a `feedback` object — see §7. Also pass `original_query=state.query`, `current_query=state.current_query`, `current_threshold=state.current_threshold`.
   
   This is what makes iteration 2+ productive (a reformulated query / adjusted threshold driven by the orchestrator's feedback).
- **Smoke:** `python src/main.py` → `test_orchestrator()` answers a document question and cites a `file_name`; logs show `[CALL_RAG] iter 1`, an `[EVALUATE]`, and either a direct `[ANSWER]` or a refine→re-search loop before answering.

### Phase 3 — Tools (L6 worker tools; leaf dependency for the Analyst)
Fill `skillab-py/src/skillab/tools/implementations.py` (editable install already active). The functions take a **single Pydantic params object** — `ToolWrapper.call(name, args)` does `params_model(**args)`, so `args["input_dfs"]` + the rest are validated into `JoinDataParams`/`FilterDataParams` before your function runs.
1. **`join_data`** → `pd.merge(params.input_dfs[0], params.input_dfs[1], left_on=params.left_key, right_on=params.right_key, how=params.how)`. (`how` is a `Literal["inner","left","right","outer"]`, default `"inner"`; Pydantic rejects anything else before you see it.)
2. **`filter_data`** → boolean-index `params.input_dfs[0]` on `params.column`. **⚠️ `params.value` is typed `str` in `FilterDataParams` — Pydantic coerces it to a string, and `analyst_plan` even instructs the LLM to emit `"value": "100"` as a string.** So:
   - For `contains`: `mask = column.astype(str).str.contains(params.value, case=False, na=False)`.
   - For **every** other operator (`== != > < >= <=`): you **must cast `params.value` to the column's dtype first**, then compare. Skipping the cast is two bugs: `>`/`<`/`>=`/`<=` raise `TypeError` (int series vs `str`), and `==`/`!=` **silently return all-`False`** (dtype mismatch never matches) — a wrong answer with no error. Concrete idiom: `typed_value = column.dtype.type(params.value)` (or `pd.Series([params.value]).astype(column.dtype).iloc[0]`), then `mask = column == typed_value`, etc.
   - Return `params.input_dfs[0][mask]`.
3. **Clean the stub docstrings.** `register_tool` uses each function's **docstring as the LLM-facing tool description** (via `ToolWrapper.to_prompt_string()` → `analyst_plan`). The stubs' docstrings contain `TODO: Implementează folosind pandas merge()` — strip those TODO lines (keep a real one-line description, ≥15 chars or `register_tool` raises) so the Analyst's catalog isn't polluted with TODO text.
- **Smoke (`scripts/smoke_tools.py`):** build two small DataFrames, call `ToolWrapper.call("join_data", {"input_dfs": [left_df, right_df], "left_key": ..., "right_key": ..., "how": "inner"})`; then `filter_data` with a **string** `value` against a **numeric** column (e.g. `{"input_dfs": [joined], "column": "amount", "operator": ">", "value": "100"}`) to prove the dtype cast works — assert the row count drops correctly. (Confirms `NotImplementedError` is gone, registry dispatch works, and the str→dtype cast is in place.)

### Phase 4 — Analyst Agent (L6 supervisor: plan → workers → synthesize)
Fill the two stubs in `src/analyst_agent.py`:
1. **`node_make_plan`** — render `analyst_plan` with `tables=self.tables_info`, `tools_catalog=self.tools_catalog`, `question=state.question`; `generate_sync`; extract the fenced JSON and parse it with **`json.loads` → a `dict`** (NOT `model_validate_json` — the payload is `{"reasoning": ..., "steps": [...]}` and `steps` is a heterogeneous list with no single model). **Then build instances per `action`**: `"query"`→`QueryStep(**step)`, `"tool"`→`ToolStep(**step)`. Return `{"reasoning": ..., "plan": [instances], "current_step": 0, "slices": {}, "step_results": []}`. **Critical contracts (the completed `node_execute_step` relies on both):**
   - **`plan` must contain `QueryStep`/`ToolStep` *instances*, not raw dicts** — `node_execute_step` uses attribute access (`step.id`, `step.action`, `step.table`, …); a raw dict would `AttributeError`.
   - **`step.table` must exactly match a `tables_config` key** (`"achizitii_directe"` / `"anunturi_initiere"`) — `_execute_query` does `self.sql_agents.get(step.table)` and returns a "No agent for table" failure on any alias. The `analyst_plan` prompt lists the real names in "TABELE DISPONIBILE", so the LLM gets them right **as long as you don't post-process/shorten them**. (Note: the *stub docstring's* example uses short names like `"achizitii"` — ignore that; it's illustrative, not the configured key.)
   
   (`_route_after_plan` goes to `execute_step` if `plan` non-empty else `synthesize`; `node_execute_step`, `_execute_query`, `_execute_tool` are already done — they call the per-table `NL2SQLAgent` workers and the registry tools, storing each successful result in `state.slices[step.id]`. A step that fails is recorded in `step_results` but **not** added to `slices` — which is why `node_synthesize` must key-guard the final slice.)
2. **`node_synthesize`** — compute `final_data` defensively: `last_id = state.plan[-1].id if state.plan else None`, then `final_data = str(state.slices[last_id].head(10)) if last_id in state.slices else ""`. **Guard the key, not just emptiness** — a failed last step (or a `synthesize` reached because the plan was empty) means `last_id` is **not** in `slices`, so `state.slices[state.plan[-1].id]` would `KeyError`. Use `.head(10)` because the template literally promises "primele 10 rânduri" and a slice can be large. Render `analyst_synthesize` with `question`, `reasoning`, `results=state.step_results`, `final_data`; `generate_sync`; return `{"answer": ..., "status": "success" if any(r.status == "success" for r in state.step_results) else "failed"}`.
- **Smoke:** **first uncomment `test_analyst()` in `main.py`'s `__main__`** (it ships commented out), then `python src/main.py` → `test_analyst()` answers a multi-step question; logs show `[PLAN]` then one `[EXECUTE] step ...` per plan step (query workers + tool steps) then `[SYNTHESIZE]`; the answer reflects the joined/filtered data.

---

## 9. Pitfalls — reference material is buggy; plus repo gotchas

You are **not** reading the lesson PDFs or `code-snippets lesson 5/` (§0). For the record, those snippets contain: files that return an **uncompiled** `StateGraph` (no `.compile()`), `...` ellipsis placeholders in conditional-edge maps, an undefined `self._do_something()`, and `invoke()` calls that omit required state keys. **Follow this plan's contracts, not half-remembered snippet code.**

Repo-specific gotchas:
1. **State is Pydantic, not TypedDict** — use `state.query` (attribute), never `state["query"]`. Nodes still **return plain dicts**.
2. **No reducers here** — a returned key *replaces* the field. The Analyst accumulates via explicit `state.step_results + [result]` / `dict(state.slices)` in the *completed* `node_execute_step`; don't add `Annotated[..., add]` reducers.
3. **Prompt registry is plain Jinja2 (NOT StrictUndefined)** — a forgotten variable renders as empty string and silently degrades the prompt. Pass every variable in §7.
4. **No JSON-extraction helper exists** — extract from ` ```json ``` ` yourself (§7). LLMs often wrap JSON in fences; `model_validate_json` on the raw response will throw if you skip the regex.
5. **`generate_sql`/`handle_error` must strip code fences** (` ```sql ` … ` ``` `) or the SQL won't execute.
6. **`node_validate_sql` is the security boundary** — must block non-SELECT/DDL/injection; `_route_after_validate` trusts `is_valid`.
7. **DataFrames live in state** — `NL2SQLState`/`AnalystState` set `arbitrary_types_allowed`; comparisons like `if df:` are ambiguous — use `.empty` / `len(df)`.
8. **`analyst_plan` returns a `{"reasoning","steps"}` object**, and `steps` is a heterogeneous list — branch on `action` to build `QueryStep` vs `ToolStep` (a flat `model_validate` won't pick the union arm reliably).
9. **`.invoke()` return-type access is inconsistent in this repo — verify before trusting either style.** The completed `node_call_rag` uses **attribute** access (`rag_result.result`, via `RAGAgent.run` → `graph.invoke`), while `main.py`'s `test_orchestrator()` uses **dict** access (`result['status']`, `result['answer']`). With a Pydantic `state_schema`, what `compiled_graph.invoke()` returns depends on the installed LangGraph version (some return the Pydantic model, some a dict). **Before writing smoke scripts, run one call and check** (`type(out)`, try both `out.status` and `out['status']`) — then match the style that works. Don't assume; this is the most likely thing to break a smoke script for a reason unrelated to your node logic.
10. **Port 5434 / wrong-server trap** — see §2a; verify pgvector is the server actually answering on 5434 before debugging "vector type" errors.
11. **Editable install** — if tool edits seem ignored, confirm `pip install -e skillab-py` ran in the active venv.
12. **`db_url` constructor param is effectively dead** — `NL2SQLAgent`/`AnalystAgent` accept `db_url`, but `node_execute_sql` (per §7/§8) uses the global `transaction()`, which reads `database.DATABASE_URL` (from `.env`), **not** `self.db_url`. The constructor default and `.env` happen to point at the same DB, so it works — but don't wire `self.db_url` into your node expecting it to matter; the real source of truth is `DATABASE_URL`.
13. **`threshold=0.0` is falsy** — the *completed* `node_search` does `state.current_threshold or self.config.default_threshold`, so a `RefinedQuery` returning `threshold=0.0` silently reverts to the default (0.25). When implementing `node_refine`, to broaden a search use a small positive value (e.g. `0.05`) or leave `threshold=None` (keep current) — never emit `0.0` expecting "no threshold."
14. **The RAG agent gets a fresh state every orchestrator iteration — prior chunks are NOT threaded into `node_refine`.** `Orchestrator.node_call_rag` calls `self.rag.run(query, feedback)`, which builds a new `RAGAgentState` with `result=None`; `refine` runs before `search`. So in `node_refine`, `state.result` is always `None` (guard it — §6 / Phase 2 step 3), `found_summary` is effectively empty, and `current_query == original_query`. The cross-iteration signal travels through `feedback` (`missing_info`/`suggestion`/`wrong_context`), **not** through threaded-back search results. This is by design — do not rewire the orchestrator to "fix" it.
15. **`rag_refine` wants flattened feedback fields, not a `feedback` object** — the template reads `{{ can_answer }}`/`{{ missing_info }}`/`{{ suggestion }}`. Passing `feedback=state.feedback` renders all three blank (silent degradation, no error). Pass `can_answer=...`, `missing_info=...`, `suggestion=...` individually.
16. **`node_synthesize` must key-guard the final slice** — a failed last step (or empty plan) means `state.plan[-1].id` is absent from `state.slices`; `state.slices[state.plan[-1].id]` then `KeyError`s. Check membership first (Phase 4 step 2).
17. **`FilterDataParams.value` is always a `str`** — Pydantic coerces it and the planner emits it quoted (`"value": "100"`). Comparing a string against a numeric column either raises (`>`/`<`/…) or silently matches nothing (`==`/`!=`). Cast `value` to the column dtype for all non-`contains` operators (Phase 3 step 2). `join_data`'s `how` and `filter_data`'s `operator` are `Literal`s, so invalid values fail at Pydantic validation, not inside your function.
18. **Tool docstring = LLM description** — `register_tool` requires a docstring (≥15 chars) and exposes it verbatim in the Analyst's tool catalog. Strip the stubs' `TODO:` lines when you implement, or the planner prompt shows TODO text.
19. **`node_make_plan` is single-shot — no retry loop guards it** (unlike NL2SQL's `handle_error`). If the LLM returns malformed JSON, `json.loads` throws and the whole Analyst run crashes. The homework demo with a capable model (Gemini/OpenAI) usually parses fine, but if you want robustness, wrap the parse in `try/except` and on failure return `{"plan": [], "status": "no_plan"}` — `_route_after_plan` then routes the empty plan straight to `synthesize` (which reports `failed` cleanly). `no_plan` is the `AnalystState.status` value reserved for exactly this.

---

## 10. Definition of done

- The orchestrator's own pgvector stack is up on 5434 (`rag_demo`), `alembic upgrade head` applied, data restored; all three tables + `document_chunks` non-empty.
- `python src/main.py` runs both demos green (**uncomment `test_analyst()` in `__main__` first** — it ships commented out):
  - **`test_orchestrator()`** — answers a document question grounded in retrieved chunks (cites `file_name`), with the evaluate→refine→answer loop working (refine improves a weak first search rather than looping uselessly to max iterations).
  - **`test_analyst()`** — produces a plan, runs NL2SQL workers + at least one tool step (join/filter), and synthesizes a correct answer from the final slice.
- `NL2SQLAgent` recovers from a bad query via the `handle_error → generate_sql` retry loop — the **second** attempt regenerates via `nl2sql_error` (different SQL, not a re-emit of the failing query), and a successful retry returns `status="success"` (not bounced back by a stale `execution_error`) — or fails cleanly after `max_retries`.
- `join_data`/`filter_data` no longer raise `NotImplementedError`.
- All edits stay within the 9 stubbed functions (+ the two tools); completed nodes, routing, graph wiring, and `ai-engineer-lab/` are untouched. Code respects §4 conventions.
```
