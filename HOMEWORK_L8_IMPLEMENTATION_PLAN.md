# Implementation Plan — Memory, Prompt Caching & Intent Classifier (Homework, Lessons 7–8)

> **Audience:** another Claude instance picking this up cold. This document is self-contained — read it fully before writing code, then read the existing files in §3. Unlike Homework L6 (which *filled blanks* in an existing scaffold), this homework **extends a fully-working system**: every L5/L6 stub is already implemented. The L8 work is **additive** — new ORM models, a new memory layer, a provider extension for caching, and a standalone intent classifier. Follow the working method of `HOMEWORK_L6_IMPLEMENTATION_PLAN.md` *exactly*; only the content differs.

---

## 0. Working agreement & context discipline (read first)

**Execution mode:** You (the implementing AI) **write the code; the user reviews.** Implement **one step at a time** — a *step is a single function / model / migration / script*, not a whole phase. After each step, pause, explain what you did and why, and hand the diff to the user for review before starting the next step. Do **not** batch steps unprompted (the "headless chicken" failure the user called out). Answering a question is **not** a go-ahead — the turn returns to the user.

**Always maintain a step-progress task list (TaskCreate/TaskUpdate)** so the user can follow along: at the start of each phase, create one task per step; mark `in_progress` when you begin, `completed` when the user accepts it.

**After every completed phase, update this plan to mark that phase `✅ DONE`** (on its `### Phase N` heading in §8). Do this as the final action of the phase so the plan always reflects which phases are finished.

**Every smoke test must be reported as an end-to-end trace, not just a pass/fail.** After running a smoke test, present: (1) an **execution-flow map** — the command, then the chain of files/methods the data passes through in execution order, as a compact diagram, **without pasting code bodies** (reference files/methods by name only); (2) the **actual input data** (the rendered prompt, the SQL DB rows persisted, the classifier predictions, the cache-usage token counts) and the **actual output data** (final state fields, returned answer, the comparison table); (3) a table mapping each console line to the file/method that emitted it. Keep it visual and concise — the goal is to *see* the pipeline working with real data.

**This is teaching mode.** The deliverable is the user's *understanding* of agent memory, prompt caching, and the LLM-vs-classical-ML cost tradeoff — not fast code. Before each step: say what it does, why, and how it fits. After: show the output and interpret it. Define new terms the first time they appear (checkpointer, repository/unit-of-work, ephemeral cache breakpoint, cache_creation vs cache_read tokens, TF-IDF, confidence threshold).

**Context discipline — treat this as seriously as the code:**
- **Do NOT re-read the heavy source artifacts.** Never re-open `lesson7.pdf`, `lesson8.pdf`, `homework lesson 8.pdf`, `code-snippets lesson 8/`, or `code-snnipets lesson 7/`. **This plan already distilled everything needed**, including the snippet bugs to avoid (§9). They are megabytes of slide images and buggy reference snippets.
- **Read only:** this plan → the specific existing files in §3 → code already on disk from earlier steps.
- **Push repo exploration into subagents** (Explore/Task) so file dumps stay out of the main thread.

**This plan is the single source of truth.** If a step forces a deviation, **edit this file** to record it before moving on.

---

## 1. Goal

The homework PDF (`homework lesson 8.pdf`) is one slide titled **"Memory, Caching & Intent Classifier — Optimizează Agentul"**, with three tasks:

| # | Task (verbatim intent) | Source lesson |
|---|---|---|
| **1** | **Conversation Memory** — add ConversationMemory to the Agent; integrate it into a **LangGraph node** (persistent context across requests); persist memory in **PostgreSQL** for long-term storage. | L8 |
| **2** | **Prompt Caching** — enable **Anthropic** prompt caching (`cache_control: ephemeral`); put the **system prompt + fixed context** in the cache; **measure tokens saved + latency reduction**. | L8 |
| **3** | **Intent Classifier (scikit-learn)** — train a **TF-IDF + LogisticRegression** classifier; training data is `query + label` over labels **`search` / `extract` / `summarize`**; write a script comparing **latency, cost, and accuracy** of the **LLM vs the classifier**. | L7 |

The `ai-orchestrator/` repo is the agent being optimized. The L5/L6 agents (`NL2SQLAgent`, `RAGAgent`, `Orchestrator`, `AnalystAgent`) are **complete and working**. The L8 homework realizes the three tasks as:

| Homework concept | Realized in this repo as |
|---|---|
| L8 conversation memory (load → invoke → save, persisted) | New `src/memory.py` (`ChatMessageRepository` + `PersistentMemory`) + new `sessions`/`chat_messages` tables (migration `004`), wired into the **`Orchestrator`** via two new graph nodes (`node_load_memory`, `node_save_memory`) and an `Orchestrator.run(query, session_id)` entry point |
| L8 Anthropic prompt caching + measurement | Extension of skillab's **`AnthropicProvider`** (system as cached content blocks + usage capture) + a large static orchestrator **system prompt**, measured by `scripts/smoke_prompt_cache.py` |
| L7 intent classifier + LLM-vs-classifier comparison | Standalone `src/intent_classifier.py` + `scripts/train_intent.py` + `scripts/compare_intent.py` (the deliverable) over labels `search`/`extract`/`summarize` |

**Acceptance demo:**
- A multi-turn conversation against the `Orchestrator` (same `session_id`) where turn 2 demonstrably uses turn-1 context, and the conversation survives a process restart (rows in `chat_messages`).
- A prompt-caching run whose accumulated `usage_log` shows one entry with `cache_creation_input_tokens > 0` (first system-block call) followed by a later entry with `cache_read_input_tokens > 0`, with a printed tokens-saved + latency-delta summary.
- `scripts/compare_intent.py` prints a table comparing LLM vs scikit-learn classifier on **latency, cost, accuracy** over a held-out test set.

---

## 2. Locked decisions (do not relitigate)

| Decision | Choice | Why |
|---|---|---|
| Memory target agent | **`Orchestrator`** (the RAG document-Q&A supervisor) | Closest to the lesson's "Document Analyst" framing; conversational follow-ups over documents ("what's *their* phone number?") are the natural memory demo. Single clean entry seam. |
| Memory mechanism | **PostgreSQL Repository + Unit-of-Work** (`sessions` + `chat_messages` tables, a `PersistentMemory` manager doing load→invoke→save), **integrated as two LangGraph nodes** | Satisfies "persist in PostgreSQL" *literally* and "integrate into the LangGraph node" *literally*; readable chat history (not opaque checkpoint blobs); matches the L8 snippet's teaching pattern. (LangGraph's built-in `PostgresSaver` is the alternative — noted in §9, not used.) |
| Prompt-caching provider | **Add Anthropic to the live path** — `pip install anthropic`, set `ANTHROPIC_API_KEY` + `ANTHROPIC_MODEL`, and **extend skillab's `AnthropicProvider`** to emit `cache_control: ephemeral` on the system block and to expose usage tokens. The memory-enabled `Orchestrator` demo runs on **Claude**. | Task 2 *mandates* Anthropic `cache_control: ephemeral`; the app currently runs on Gemini and `anthropic` isn't installed. Editing the vendored provider *is* part of this homework (skillab is installed `-e`). |
| Editing skillab is in-scope | **Yes — `skillab-py/src/skillab/llm/providers/anthropic.py`** is an allowed edit (editable install). | Mirrors L6's "editing `implementations.py` is part of the homework". The provider has no kwargs/usage surface today (§7), so caching is unreachable without it. |
| Anthropic model | Set **`ANTHROPIC_MODEL=claude-sonnet-4-6`** in `.env` (the provider's hardcoded `default_model` is the stale `claude-sonnet-4-20250514`). Do **not** silently edit the skillab default — override via env. | Current, supports prompt caching. **Present** the idea of bumping the stale default to the user; don't do it unsolicited. Confirm model id + min-cacheable-tokens + pricing via the `claude-api` skill at impl time. |
| Intent classifier scope | **Standalone + comparison script** — train, persist, and deliver the LLM-vs-classifier comparison. **Do NOT rewire the live graph** with a `route_by_intent` node. | Exactly what the slide asks; minimal blast radius. (Wiring it into a router is the L7 keystone but out of scope here — noted in §9.) |
| State type | **Pydantic `BaseModel`** (existing `state.py` convention) — attribute access in nodes, return partial dicts. | Matches the scaffold; do not switch to TypedDict. |
| Reducers | New `OrchestratorState.history` is **loaded once** by `node_load_memory` and read by `node_answer`; **no `Annotated` reducer**. | Consistent with the repo's no-reducer convention (§9 of L6). |
| Don't touch | `ai-engineer-lab/`, the completed L5/L6 nodes/routing/graph-wiring (except the documented Orchestrator wiring additions for memory), and the NL2SQL/Analyst agents. | Out of scope. |

### 2a. Infra (reuse the existing stack; add two tables)

Same Postgres stack as L6: `pgvector/pgvector:pg16`, **host port 5434**, db/user/pass `rag_demo` / `demo` / `demo123`, `DATABASE_URL=postgresql://demo:demo123@localhost:5434/rag_demo`. **No new container.** The memory tables (`sessions`, `chat_messages`) are added via a new Alembic migration on the **same** database. New Python deps: `anthropic` (prompt caching), `scikit-learn` + `joblib` (intent classifier). `sentence-transformers` is already present (not needed for this homework's three tasks).

---

## 3. Read these existing files first (then honor their contracts)

The repo lives at `/Users/vali/Work/AI/AI Engineer/ai-orchestrator/`.

- `HOMEWORK_L6_IMPLEMENTATION_PLAN.md` — the **method template**. Working agreement, smoke-trace format, conventions. This L8 plan inherits all of it.
- `src/state.py` — all Pydantic state schemas. You will **add** `ConversationMessage` and two fields to `OrchestratorState` (§6). Note `OrchestratorState` has `Config.extra = "allow"`.
- `src/orchestrator.py` — `Orchestrator`. **`build_graph()` is the only entry today** (callers do `app = orch.build_graph(); app.invoke(OrchestratorState(query=...))`). `node_evaluate` and `node_answer` are COMPLETE — both build `context` from `state.rag_result.results` and call `self.llm.generate_sync([{"role":"user","content": prompt}])` with `rag_evaluate` / `rag_answer`. You will **add** `node_load_memory`, `node_save_memory`, an `Orchestrator.run(query, session_id)` method, and extend the graph wiring (§8 Phase 1). `.invoke()` returns a **dict** here (`result['status']`).
- `src/database.py` — `transaction()` context manager (`with transaction() as db: ...`), `SessionLocal` (uses `expire_on_commit=False`), `DATABASE_URL`. Use `transaction()` for memory reads/writes.
- `src/models.py` — SQLAlchemy 2.0 declarative `Base` + `DocumentChunk`, `AchizitieDirecta`, `AnuntInitiere`. You will **add** `Session` and `ChatMessage` ORM models here. `EMBEDDING_DIM = 384`.
- `src/repositories.py` — the repository pattern to mirror (`DocumentChunkRepository`, etc.: `__init__(self, session)`, methods using `self.session.query(...).filter_by(...)` / `self.session.add(...)`). Your `ChatMessageRepository` follows this shape — **param is `session`, ORM-query style, not `select()`** (corrected 2026-06-23; see §7).
- `src/main.py` — `test_orchestrator()`, `test_analyst()`. Resolves provider/model from `.env` via an alias map (`gemini→google`, `ollama→local`) and `_MODEL_ENV_VARS`. You will **add** a `test_memory()` (or extend) demo that calls `Orchestrator.run(...)` on Claude across turns.
- `alembic/versions/` — migrations are **string-id** style: `001 → 002 → 003`. Latest is **`003`**. Add `004_create_chat_sessions_messages.py` with `revision='004'`, `down_revision='003'`, hand-written `op.create_table(...)` (mirror `003`). `alembic/env.py` reads `target_metadata = Base.metadata` from `models`.
- `prompts/*.yaml` — single-string Jinja2 templates, **no system-prompt concept** today; each is sent as one user message. `analyst_plan.yaml` is the **only** template with a `{% if history %}…{% for msg in history %}{{ msg.role }}: {{ msg.content }}{% endfor %}…{% endif %}` slot — **copy that pattern** into `rag_answer.yaml`. You will also **add** a new static system-prompt template (`prompts/orchestrator_system.yaml`) for caching.
- `skillab-py/src/skillab/llm/base.py` — `Message = dict[str,str]` (`{"role","content"}`, content is `str`); `generate_sync(messages) -> str` (concrete, runs async `generate` on a class loop). **Returns a bare `str`; no usage surface.**
- `skillab-py/src/skillab/llm/providers/anthropic.py` — `AnthropicProvider`. The file you extend in Phase 2. Contracts that matter: `is_configured()` keys off `ANTHROPIC_API_KEY`; `default_model` is stale (override via `ANTHROPIC_MODEL` — §2); `_prepare_messages` splits the system message out as a **plain str** (not content blocks); `generate()` returns `response.content[0].text` and **drops `response.usage`, with no kwargs passthrough**. Read the current signatures before editing.
- `skillab-py/src/skillab/llm/registry.py` — `get_llm(provider, model, temperature=0.0, cached=True)`; instances cached by `name:model:temperature`. Pass `cached=False` for a fresh instance.

**New files to create:** `src/memory.py`, `alembic/versions/004_*.py`, `prompts/orchestrator_system.yaml`, `src/intent_classifier.py`, `scripts/train_intent.py`, `scripts/compare_intent.py`, `scripts/smoke_memory.py`, `scripts/smoke_prompt_cache.py`, plus intent data under `data/intent/`. Edits to existing files: `src/state.py`, `src/models.py`, `src/orchestrator.py`, `src/main.py`, `prompts/rag_answer.yaml`, `skillab-py/.../anthropic.py`, `requirements.txt`, `.env`.

---

## 4. Hard conventions (from `~/.claude/CLAUDE.md` and the scaffold's style)

1. **No 1–2 letter variable names.** `chat_message`, not `cm`; `dataframe`/`result_rows`, not `df` where avoidable. (Memory recall: the user explicitly wants `df`/`col`/`tc` spelled out.)
2. **Avoid explanatory comments.** Prefer clear names and small helpers.
3. **Present ideas before doing them.** No unsolicited renames/refactors. Touch only what each step names. (E.g. don't bump the skillab default model without asking — override via `.env`.)
4. **Plan-first, one step at a time, smoke-test each phase** (§0).
5. **Match surrounding style:** Pydantic-state attribute access; `self.llm.generate_sync([{...}])`; `self.prompts.render(name, **vars)`; repositories take `db` and use `select(...)`; nodes return a partial `dict`. Mirror the COMPLETE `node_answer`/`node_evaluate` (Orchestrator) and the existing repositories.
6. **Smoke tests are versioned `.py` files under `scripts/`**, named for what they exercise (`smoke_memory.py`, `smoke_prompt_cache.py`, `compare_intent.py`), run via `python scripts/<name>.py`.
7. **Concise answers** (memory recall): short, on-point; no long explanations.
8. **English for any comment you write or touch.** New/edited comments are in English (existing untouched Romanian comments stay as-is). User instruction, 2026-06-23.

---

## 5. Repo map (new = 🆕, edited = ✏️, untouched-complete = ✅)

```
ai-orchestrator/
├── docker-compose.yaml        ✅ pgvector on 5434 (reused; no new container)
├── requirements.txt           ✏️ add anthropic, scikit-learn, joblib
├── .env                        ✏️ add ANTHROPIC_API_KEY, ANTHROPIC_MODEL
├── alembic/versions/
│   ├── 001/002/003            ✅
│   └── 004_create_chat_sessions_messages.py   🆕 sessions + chat_messages
├── data/
│   └── intent/                🆕 training_data.json, test_data.json, intent_classifier.joblib
├── prompts/
│   ├── rag_answer.yaml        ✏️ add {% if history %} slot (mirror analyst_plan)
│   ├── query_contextualize.yaml   🆕 history + query → standalone query (follow-up retrieval)
│   └── orchestrator_system.yaml   🆕 large static system prompt (cache target, ≥ model min tokens)
├── scripts/
│   ├── smoke_memory.py        🆕 multi-turn + restart persistence
│   ├── smoke_prompt_cache.py  🆕 cache_creation vs cache_read + latency
│   ├── train_intent.py        🆕 TF-IDF + LogisticRegression → joblib
│   └── compare_intent.py      🆕 DELIVERABLE: LLM vs classifier latency/cost/accuracy
├── src/
│   ├── state.py               ✏️ add ConversationMessage; OrchestratorState.session_id + history
│   ├── models.py              ✏️ add Session, ChatMessage ORM models
│   ├── memory.py              🆕 ChatMessageRepository + PersistentMemory (load/save)
│   ├── orchestrator.py        ✏️ + node_load_memory, node_save_memory, run(), graph wiring
│   ├── intent_classifier.py   🆕 load joblib + detect_intent(query)->(label, confidence)
│   ├── main.py                ✏️ + test_memory() on Claude
│   └── (rag_agent/nl2sql_agent/analyst_agent/rag_service/database/repositories)  ✅ untouched
└── skillab-py/src/skillab/llm/providers/
    └── anthropic.py           ✏️ system→cached content blocks + usage capture
```

---

## 6. State & data schemas (the contracts)

**New Pydantic state (`src/state.py`):**
- `ConversationMessage` — `role: str`, `content: str`. (Attribute access `.role`/`.content` so it works in the `rag_answer` Jinja loop, mirroring `analyst_plan`.)
- `OrchestratorState` gets three new fields: `session_id: str = ""`, `history: list[ConversationMessage] = []`, and `original_query: str = ""`. (`extra="allow"` already lets these through, but declare them explicitly for clarity.) **`original_query` preserves the user's literal input** — `node_load_memory` overwrites `state.query` with a history-contextualized standalone query (so retrieval works on follow-ups), and `node_save_memory` persists `original_query`, not the rewritten one.

**New ORM models (`src/models.py`), mirroring the L8 snippet schema:**
- `Session` — `id` (PK, str/uuid or int), `created_at` (timestamp, server default). 1:N → `chat_messages`.
- `ChatMessage` — `id` (PK, autoincrement int), `session_id` (FK → sessions.id, indexed), `role` (str: `"user"`/`"assistant"`), `content` (text), `created_at` (timestamp, server default). The `id` is the **tiebreaker** for ordering within the same timestamp.

**Memory layer (`src/memory.py`):**
- `ChatMessageRepository(session)` — `add(session_id, role, content)`; `latest(session_id, limit)` → `self.session.query(ChatMessage).filter_by(session_id=...).order_by(created_at.desc(), id.desc()).limit(limit).all()`, then **`reversed()`** to chronological order. (Mirror the existing repositories' `self.session.query(...).filter_by(...)` style — **not** `select()`; corrected 2026-06-23 to match actual `src/repositories.py`.) `latest` returns ORM rows; `PersistentMemory.load_messages` maps them to `ConversationMessage`.
- `PersistentMemory(window=10)` — `load_messages(session_id) -> list[ConversationMessage]` (opens a `transaction()`, calls `repo.latest`, maps ORM rows → `ConversationMessage`); `save_message(session_id, role, content)` (opens a `transaction()`, `repo.add`, commit via the context manager). Also `ensure_session(session_id)` (insert the `Session` row if absent) so the FK is satisfiable.

**Mapping to the homework:** `PersistentMemory.load_messages` + `save_message` wrapping the graph invocation **is** the L8 "load → invoke → save"; the `chat_messages` table **is** "persist in PostgreSQL for long-term storage"; the two new graph nodes **are** "integrate into the LangGraph node".

---

## 7. Shared idioms & new contracts (use these verbatim)

**LLM call** (unchanged): `response = self.llm.generate_sync([{"role": "user", "content": prompt}])` → `str`.

**Prompt render** (unchanged): `self.prompts.render("template_name", var1=..., ...)` → `str`. Plain Jinja2, no `StrictUndefined` → a missing scalar renders blank; a missing var used in a `{% for %}`/attribute access raises `UndefinedError`. **Always pass `history=[]`** to `rag_answer` when there is none.

**DB access in memory layer** (corrected 2026-06-23 — use the repo's ORM-query style, matching `src/repositories.py`, not `select()`):
```python
from database import transaction
from memory import ChatMessageRepository
with transaction() as session:
    rows = ChatMessageRepository(session).latest(session_id, limit)  # already reversed -> chronological
    # map rows -> list[ConversationMessage] inside the block (expire_on_commit=False makes after-block safe too)
```
`ChatMessageRepository.latest` internally: `self.session.query(ChatMessage).filter_by(session_id=...).order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).limit(limit).all()` then `reversed()`.

**Anthropic prompt caching (Phase 2 — the new provider contract):**
- `messages.create(...)`'s `system` must be a **list of content blocks** to attach a cache breakpoint:
  ```python
  system=[{"type": "text", "text": system_text,
           "cache_control": {"type": "ephemeral"}}]
  ```
- Usage lives on `response.usage`: `input_tokens`, `output_tokens`, **`cache_creation_input_tokens`** (written to cache on a miss), **`cache_read_input_tokens`** (served from cache on a hit, billed ~0.1×).
- **Minimum cacheable block:** ~**1024 tokens** for Claude 3.x, ~**2048 tokens** for Sonnet 4.x. A breakpoint on a block below the minimum simply isn't cached (`cache_creation=0`). **The `orchestrator_system.yaml` prompt must exceed the chosen model's minimum** or the demo shows nothing. Confirm the exact number for `claude-sonnet-4-6` via the `claude-api` skill.
- **Opt-in, not always-on:** add a `cache_system: bool = False` flag to `AnthropicProvider` (constructor + settable attribute). Only attach `cache_control` when `cache_system` is True **and** a system message is present. This keeps NL2SQL/Analyst (which send no system message) and any short-prompt path unaffected. The memory `Orchestrator` demo sets it on.
- **Expose usage without breaking the `str` contract — accumulate, do not overwrite:** keep `generate_sync` returning `str`, but **append** `response.usage.model_dump()` to a `self._usage_log` list inside `generate` (the SDK `Usage` is a Pydantic object — use `.model_dump()`, **not** `dict(...)`). Expose a `usage_log` property and a `reset_usage()` method; `last_usage` may remain as `usage_log[-1]` for convenience. **A single slot is wrong here:** one `Orchestrator.run` makes *many* `generate_sync` calls — the RAG agent (which shares `self.llm`), then `node_evaluate` (cache **creation**), then `node_answer` (cache **read**) — and each overwrites a single slot. `cache_creation` happens exactly once ever (the *first* system-block call) and is never the *final* call of any run, so a single `last_usage` read at run boundaries can only ever show a cache **read**. The measurement script must `reset_usage()`, do one run, then scan the whole `usage_log`.
- **SDK version:** prompt caching is GA in current `anthropic` SDKs (no beta header). Only an *old* pinned SDK needs `extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}`. Pin a recent `anthropic`; verify the exact requirement via the `claude-api` skill.
- **System message must reach the provider — gated, not unconditional:** today the Orchestrator sends only a user message. In `node_evaluate`/`node_answer`, prepend a system message **only when `getattr(self.llm, "cache_system", False)` is True**: `[{"role":"system","content": system_text}, {"role":"user","content": prompt}]`. Gating matters: the existing `test_orchestrator()` runs these same nodes on **Gemini**, and an unconditional 2048-token system prompt would silently change its behavior. `_prepare_messages` extracts the system message; the provider edit turns it into the cached block. (Both `node_evaluate` and `node_answer` are edited for caching — authorized in §2/§8.)

**Intent classifier (Phase 3) contracts:**
- Training: `sklearn.pipeline.Pipeline([("tfidf", TfidfVectorizer(ngram_range=(1,2))), ("clf", LogisticRegression(max_iter=1000))])`, `.fit(texts, labels)`, `joblib.dump(pipeline, "data/intent/intent_classifier.joblib")`. Labels are exactly `search` / `extract` / `summarize`.
- Inference (`src/intent_classifier.py`): `detect_intent(query) -> (label: str, confidence: float)` using `pipeline.predict([query])[0]` and `max(pipeline.predict_proba([query])[0])`.
- LLM baseline: a classification prompt instructing Claude to return one of the three labels; parse the label out of the response.
- Comparison (`scripts/compare_intent.py`): over a held-out `test_data.json`, run both classifiers; measure **latency** (`time.perf_counter()` per call, averaged), **cost** (classifier ≈ `$0`; LLM = tokens × current per-MTok price — **verify pricing via `claude-api` skill**), **accuracy** (fraction matching ground-truth label). Print a comparison table.

---

## 8. Phased tasks (each phase ends in a smoke test; each function/model/script is its own step)

### Phase 0 — Setup & infra (no agent code; prepare the environment)
1. `requirements.txt`: add `anthropic`, `scikit-learn`, `joblib`. `pip install -r requirements.txt` (+ confirm `pip install -e skillab-py` still active).
2. `.env`: add `ANTHROPIC_API_KEY=<key>` and `ANTHROPIC_MODEL=claude-haiku-4-5`. (Keep the existing Gemini config for the L5/L6 agents.)
3. Confirm the 5434 pgvector stack is up (`docker compose up -d`); `DATABASE_URL` reachable.
- **Smoke:** `get_llm(provider="anthropic")` returns a configured provider (`is_configured()` True); one `generate_sync` round-trips on `claude-haiku-4-5`; SQLAlchemy connects to `DATABASE_URL`. **Verified facts (via `claude-api` skill, 2026-06-23):** model id `claude-haiku-4-5`; min cacheable prefix **4096 tokens**; pricing **$1.00 / 1M input, $5.00 / 1M output**; cache reads bill ~0.1×, writes ~1.25× (5-min ephemeral TTL). **Cost-driven choice: Haiku 4.5 over Sonnet 4.6 — caching demo is Anthropic-specific so "free" isn't viable; Haiku is the cheapest capable Claude.**

### Phase 1 — Conversation Memory (Task 1: L8) — ✅ DONE

> **Why contextualization is mandatory here (verified design fact, do not skip):** the Orchestrator is RAG — the answer is gated by *retrieval*, and retrieval embeds `state.query`. A follow-up like "Și ce adresă?" has no entity, so it retrieves the wrong/no chunks; worse, the COMPLETE `node_answer` **short-circuits to a "failed" message when there are no results** and never renders the history-aware prompt. So history in the answer prompt alone is cosmetic. The fix: `node_load_memory` rewrites the follow-up into a **standalone query** using history and overwrites `state.query` (so the untouched `node_call_rag` retrieves correctly), while `original_query` preserves the literal user input for persistence.

1. **`src/state.py`** — add `ConversationMessage(role, content)`; add `session_id: str = ""`, `history: list[ConversationMessage] = []`, `original_query: str = ""` to `OrchestratorState`.
2. **`src/models.py`** — add `Session` + `ChatMessage` ORM models (§6).
3. **`alembic/versions/004_create_chat_sessions_messages.py`** — hand-written `op.create_table` for both tables (mirror `003`); `revision='004'`, `down_revision='003'`; `created_at` via `sa.func.now()` server default. Then `alembic upgrade head`.
4. **`src/memory.py` → `ChatMessageRepository`** — `add` + `latest` (§6/§7). Map ORM rows → `ConversationMessage` **inside the `transaction()` block**.
5. **`src/memory.py` → `PersistentMemory`** — `ensure_session`, `load_messages`, `save_message` (window default 10).
6. **`prompts/rag_answer.yaml`** — add the `{% if history %}` block (copy from `analyst_plan.yaml`); the answer prompt now consumes prior turns. (Pass `history=[]` when none — §9.)
7. **`orchestrator.node_load_memory`** (new START node) — **no-op when `state.session_id` is falsy** (return `{}`). Else: `history = PersistentMemory().load_messages(session_id)`; set `original_query = state.query`; **if `history` is non-empty**, render a new `query_contextualize` prompt (history + current query → standalone query), `generate_sync`, and use that as the new `query`; if history empty, keep `query` unchanged. Return `{"history": history, "original_query": original_query, "query": standalone_query}`.
8. **`prompts/query_contextualize.yaml`** (new template, used by step 7) — given `history` (loop) + `query`, produce a single self-contained query string (no fences, just the rewritten query). One cheap LLM call; only fires when history exists.
9. **`orchestrator.node_answer`** (edit the COMPLETE node minimally) — pass `history=state.history` into the `rag_answer` render. *(Record as a deviation if it grows beyond adding the kwarg.)*
10. **`orchestrator.node_save_memory`** (new node before END) — **no-op when `session_id` is falsy** (return `{}`). Else `PersistentMemory().save_message(session_id, "user", state.original_query or state.query)` then `save_message(session_id, "assistant", state.answer)`; return `{}`. **Persist `original_query`, not the rewritten `query`.**
11. **Graph wiring** — `START → load_memory → call_rag → evaluate → (loop call_rag | answer) → save_memory → END`. (Extend `build_graph()`; documented Orchestrator-wiring exception in §2.)
12. **`Orchestrator.run(query, session_id)`** — build the graph (cache the compiled graph; build once), `invoke(OrchestratorState(query=query, session_id=session_id))`, return the result dict. The single conversational entry seam.
- **Smoke (`scripts/smoke_memory.py`):** turn 1 `run("Ce contact are DataPro?", session_id="s1")`; turn 2 `run("Și ce adresă are?", session_id="s1")` — `node_load_memory` rewrites turn 2 to a standalone query (e.g. "Ce adresă are DataPro?"), retrieval succeeds, the `rag_answer` prompt **contains turn-1 history**, and the answer is about DataPro's address. `chat_messages` has 4 rows for `s1` with the **original** user texts. Re-run the script (simulating restart) → history loads from Postgres, row count grows. Report: the rewritten query, the persisted rows, and the history-injected prompt.

### Phase 2 — Prompt Caching (Task 2: L8) — one step per item
1. **`prompts/orchestrator_system.yaml`** — author a large **static** "Document Analyst" system prompt (role, corpus domain description, answering rules, format guidance) that **exceeds the model's min cacheable tokens** (target ≥ **4096** for Haiku 4.5 — confirmed via `claude-api`; a 2048-token prompt would silently NOT cache on Haiku). Mostly static; no per-query Jinja vars.
2. **`AnthropicProvider`** — add `cache_system: bool = False` (constructor + settable attribute) and a `self._usage_log` list with a `usage_log` property + a `reset_usage()` method (`last_usage` = `usage_log[-1]` optional convenience).
3. **`AnthropicProvider.generate`** — when `cache_system` is True **and** a system message is present, build `system=[{"type":"text","text":..., "cache_control":{"type":"ephemeral"}}]`; otherwise keep the existing plain-str/`[]` system path. **Always** `self._usage_log.append(response.usage.model_dump())` (Pydantic object → `.model_dump()`, not `dict(...)`; **append, never overwrite** — §7).
4. **Orchestrator caching path** — load `orchestrator_system.yaml`; in `node_evaluate`/`node_answer` prepend it as a system message **only when `getattr(self.llm, "cache_system", False)`** (so the Gemini `test_orchestrator()` path is unaffected — §7). Run the demo with `get_llm("anthropic", cached=False)` then `.cache_system = True`.
5. **Measurement (`scripts/smoke_prompt_cache.py`)** — use a **known-retrieving** query (e.g. "Ce contact are DataPro?") so the LLM is actually called (a no-results query short-circuits `node_evaluate`/`node_answer` and sends no system block). **Measure within a single run via the `usage_log`, not at run boundaries** (§7): `llm.reset_usage()`, one `Orchestrator.run(...)`, then scan `llm.usage_log` and assert *some* entry has `cache_creation_input_tokens > 0` (the first system-block call, `node_evaluate`) and a *later* entry has `cache_read_input_tokens > 0` (`node_answer`). Print tokens-saved (cache_read billed ~0.1×) and the wall-clock latency delta between the creation call and the read call. A second back-to-back run (within the ~5-min TTL) is optional and will show *only* reads — useful for the latency story, useless for proving creation.
- **Smoke:** the trace shows the creation entry and the read entry from the `usage_log` side by side, the token-savings math, and the latency reduction. **Why single-run, not two-run:** `cache_creation` fires exactly once ever — the first system-block call inside run 1 (`node_evaluate`) — and is never the final `generate_sync` of any run (the RAG agent and `node_answer` overwrite a single slot), so only the accumulated `usage_log` can observe both creation and read. (If no entry has `cache_read>0`, the system block is under the min or the TTL lapsed — §9.)

### Phase 3 — Intent Classifier (Task 3: L7) — one step per item
1. **`data/intent/training_data.json`** — `[{text, label}]` over `search`/`extract`/`summarize` (aim ~30–60 examples/label; Romanian + English queries matching the document/data domain).
2. **`data/intent/test_data.json`** — a held-out labeled set (not in training).
3. **`scripts/train_intent.py`** — build the TF-IDF + LogisticRegression `Pipeline`, `.fit`, `joblib.dump` to `data/intent/intent_classifier.joblib`; print train accuracy.
4. **`src/intent_classifier.py`** — `detect_intent(query) -> (label, confidence)` (lazy-load the joblib at import/first call).
5. **LLM baseline** (inside `compare_intent.py` or a small helper) — a Claude classification prompt returning one of the three labels; parse it.
6. **`scripts/compare_intent.py`** (DELIVERABLE) — over `test_data.json`, run both; print a table of **latency** (avg ms/call), **cost** (LLM tokens×price vs ~$0), **accuracy** (vs ground truth). Use `time.perf_counter()`; verify LLM pricing via `claude-api`.
- **Smoke:** `python scripts/compare_intent.py` prints the comparison table; the classifier is ~100× faster, ~free, within a few points of the LLM's accuracy.

---

## 9. Pitfalls — reference material is buggy; plus repo gotchas

Reference snippets you are **not** re-reading (§0) contained, for the record: an `async detect_intent_llm` called without `await` and missing its `llm` arg (slides 18/20); a `detect_intent_sklearn` referenced but never defined (slide 38); a `ConversationEntityMemory` import that's **removed in LangChain ≥1.0**; an order-fragile `store` dict referenced before definition; a `SmartCache` with no `set` method; and embedding caches that rewrite the whole JSON file per miss. **Follow this plan's contracts, not half-remembered snippet code.**

Repo-/task-specific gotchas:
1. **State is Pydantic, not TypedDict** — `state.session_id` (attribute), nodes return plain dicts. `OrchestratorState` is `extra="allow"`, but declare new fields explicitly.
2. **`.invoke()` returns a dict here** — `result['status']`/`result['answer']` (matches `main.py`). Don't assume attribute access on the graph output.
3. **`rag_answer` now iterates `history`** — once you add the `{% for msg in history %}` loop, **always pass `history=[]`** when there's none, or it raises `UndefinedError` (plain Jinja2, no StrictUndefined).
3a. **Decisions enforced at point-of-use (don't re-derive):** memory needs query contextualization (§8 Phase 1 step 7); gate system-prompt injection on `cache_system` (§7, Phase 2 step 4); both memory nodes no-op on empty `session_id` (§8 steps 7/10); `response.usage.model_dump()` not `dict(...)` (§7); persist `original_query` not the rewrite (§6, step 10). These are *why*-d where they're applied — listed here only as a checklist.
4. **Anthropic system caching needs content *blocks*, not a string** — the current provider sends `system` as a plain `str`; a `cache_control` only attaches to a `{"type":"text",...}` block. (§7)
5. **Min cacheable tokens — 4096 for Haiku 4.5** (Sonnet 4.x is 2048; 3.x is 1024). We're on Haiku, so `orchestrator_system.yaml` must clear **4096** or `cache_creation`/`cache_read` stay 0 and the demo proves nothing. Pad with genuine static content. (Verified via `claude-api` 2026-06-23 — §0/Phase 0 smoke.)
6. **Ephemeral cache TTL ≈ 5 minutes** — the two measurement calls must be back-to-back; a slow gap between them yields `cache_read=0`. Don't insert `sleep`/manual pauses between them.
7. **`generate_sync` returns a bare `str`** — usage is only reachable via the `usage_log` you add; don't expect the graph nodes to surface tokens. **Accumulate, don't overwrite:** one `run` makes many `generate_sync` calls (RAG agent → `node_evaluate` → `node_answer`); `cache_creation` fires once (first system-block call) and is never the last call, so a single-slot `last_usage` read at run end only ever shows a cache read. Scan the whole `usage_log` from one run (§7/§8 Phase 2).
8. **Provider instance caching** — `get_llm` caches by `name:model:temperature`. To get a provider with `cache_system=True` without poisoning the shared cached instance used by other agents, use `get_llm("anthropic", cached=False)` (fresh instance) then set `.cache_system=True`.
9. **Stale default model** — the provider's `default_model` (`claude-sonnet-4-20250514`) is retired. Override via `.env ANTHROPIC_MODEL=claude-haiku-4-5`; don't edit the skillab default without asking the user first.
10. **FK ordering** — `chat_messages.session_id` references `sessions.id`; `PersistentMemory.save_message` must `ensure_session` first or the insert violates the FK.
11. **Ordering tiebreaker** — order `chat_messages` by `(created_at DESC, id DESC)` then `reversed()`; same-second inserts need the `id` tiebreaker or history scrambles.
12. **`expire_on_commit=False`** — `SessionLocal` keeps attributes after commit (L6 Deviation 1), so reading `ChatMessage` fields after the `transaction()` block is safe. Still map ORM rows → `ConversationMessage` inside or right after the block.
13. **Gemini free tier ≈ 20 req/day/model** (memory) — the L5/L6 agents on Gemini, plus the orchestrator's evaluate/refine loop (up to 3×), burn quota fast. The memory + caching demos run on **Claude**, so Anthropic key/quota is what matters there; keep Gemini-side smoke runs minimal.
14. **Editable install** — if the `anthropic.py` provider edit seems ignored, confirm `pip install -e skillab-py` is active in the venv and `anthropic` is installed.
15. **Don't rewire the live graph for intent** (Task 3 is standalone, §2) — no `route_by_intent` conditional edge. Keep the classifier off the agent's hot path.
16. **Cost numbers are illustrative in the lessons** — for `compare_intent.py` use **current** published Anthropic pricing (verify via `claude-api`), not the slides' `$30/1000` figures.

---

## 10. Definition of done

- **Task 1 (Memory):** `Orchestrator.run(query, session_id)` loads prior turns from Postgres, threads them into the `rag_answer` prompt, and saves the new turn; a multi-turn conversation in one `session_id` demonstrably uses earlier context, and `chat_messages` rows survive a process restart. Memory is integrated as LangGraph nodes (`load_memory`/`save_memory`).
- **Task 2 (Prompt Caching):** the extended `AnthropicProvider` emits `cache_control: ephemeral` on a ≥-min-token system block and accumulates a `usage_log`; a single run's `usage_log` shows `cache_creation_input_tokens>0` (first system-block call) then a later `cache_read_input_tokens>0`, with printed tokens-saved + latency-reduction numbers.
- **Task 3 (Intent Classifier):** a trained TF-IDF+LogReg model over `search`/`extract`/`summarize` is persisted; `scripts/compare_intent.py` prints a latency/cost/accuracy table comparing the LLM and the classifier on a held-out set.
- All new code respects §4 conventions; the L5/L6 agents, routing, and `ai-engineer-lab/` are untouched except the documented Orchestrator memory-wiring additions and the in-scope skillab `AnthropicProvider` extension.
```
