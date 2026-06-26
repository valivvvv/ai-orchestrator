# Temă: Multi-Agent System

Două sisteme:
1. **Orchestrator + RAG** - caută în documente
2. **Analyst + NL2SQL** - query-uri SQL

## Arhitectură

### 1. Orchestrator + RAG (Hierarchical Multi-Agent)

```
┌──────────────────────────────────────────────────────────────────┐
│                        ORCHESTRATOR                               │
│                        (Supervizor)                               │
│                                                                   │
│    ┌──────────┐      ┌──────────┐      ┌────────┐                │
│    │ call_rag │ ───► │ evaluate │ ───► │ answer │ ───► END       │
│    └──────────┘      └──────────┘      └────────┘                │
│         ▲                  │                                      │
│         │                  │ can_answer=false                     │
│         │                  │ + feedback                           │
│         └──────────────────┘                                      │
│                                                                   │
│    max 3 iterații                                                 │
└──────────────────────────────────────────────────────────────────┘
         │                   ▲
         │ query +           │ RAGSearchResult
         │ feedback          │
         ▼                   │
┌──────────────────────────────────────────────────────────────────┐
│                         RAG AGENT                                 │
│                         (Worker)                                  │
│                                                                   │
│    ┌────────┐      ┌────────┐                                    │
│    │ refine │ ───► │ search │ ───► END                           │
│    └────────┘      └────────┘                                    │
│                                                                   │
│    refine: dacă are feedback, rafinează query-ul                 │
│    search: caută în pgvector, returnează chunks                  │
└──────────────────────────────────────────────────────────────────┘
```

**Flow:**
1. Orchestrator apelează RAG Agent cu query
2. RAG Agent caută și returnează chunks
3. Orchestrator evaluează: "Pot răspunde?"
4. Dacă NU → trimite feedback, RAG Agent rafinează și caută din nou
5. Dacă DA → generează răspuns final

**Prompturi:** `rag_evaluate.yaml`, `rag_answer.yaml`, `rag_refine.yaml`

### 2. Analyst + NL2SQL (Hierarchical Multi-Agent)

```
┌──────────────────────────────────────────────────────────────────┐
│                      ANALYST AGENT                                │
│                      (Supervizor)                                 │
│                                                                   │
│    ┌───────────┐      ┌──────────────┐      ┌─────────────┐      │
│    │ make_plan │ ───► │ execute_step │ ───► │ synthesize  │──►END │
│    └───────────┘      └──────────────┘      └─────────────┘      │
│                              │  ▲                                 │
│                              └──┘ loop                            │
│                                                                   │
│    Plan: [QueryStep, QueryStep, ToolStep, ...]                    │
│    Slices: {"q1": DataFrame, "q2": DataFrame, "joined": DataFrame}│
└──────────────────────────────────────────────────────────────────┘
           │                              │
           │ QueryStep                    │ ToolStep
           ▼                              ▼
┌──────────────────────────────┐    ┌─────────────────────────┐
│        NL2SQL AGENT          │    │      TOOL REGISTRY      │
│         (Worker)             │    │                         │
│                              │    │  join_data(dfs, keys)   │
│  get_context                 │    │  filter_data(df, cond)  │
│      │                       │    │                         │
│      ▼                       │    └─────────────────────────┘
│  generate_sql                │
│      │                       │
│      ▼                       │
│  validate_sql ───┬───► execute_sql ───┬───► END (success)
│                  │           │        │
│                  │ invalid   │ error  │
│                  ▼           ▼        │
│             handle_error ◄────────────┘
│                  │
│            retry < max?
│             yes │ no
│                 ▼  ▼
│         generate_sql  END (failed)
└──────────────────────────────┘
```

**Flow Analyst:**
1. `make_plan` - LLM generează plan cu QueryStep și ToolStep
2. `execute_step` - execută fiecare pas:
   - QueryStep → apelează NL2SQL Agent → DataFrame în `slices[id]`
   - ToolStep → apelează tool (join/filter) → DataFrame în `slices[id]`
3. `synthesize` - LLM generează răspuns din rezultate

**Flow NL2SQL:**
1. `get_context` - încarcă schema tabelului
2. `generate_sql` - LLM generează SQL
3. `validate_sql` - validează cu sqlparse
4. `execute_sql` - execută în DB → DataFrame
5. `handle_error` - dacă eroare, LLM corectează SQL și retry

**Prompturi:** `analyst_plan.yaml`, `analyst_synthesize.yaml`, `nl2sql_generate.yaml`, `nl2sql_error.yaml`

## Setup

```bash
pip install -r requirements.txt
pip install -e skillab-py

docker-compose up -d   # Postgres pe portul host 5434
alembic upgrade head

# Restaurează date (694k achiziții, 8k anunțuri, 135 chunks)
docker exec -i ai-orchestrator-postgres-1 pg_restore -U demo -d rag_demo --data-only < data/rag_demo.dump

cp .env.example .env  # editează API key; DATABASE_URL pe portul 5434
```

## Temă L8 — cum se testează

Cele trei task-uri ale temei (Memory, Prompt Caching, Intent Classifier) se rulează din rădăcina repo-ului, după setup.

### Setup (o singură dată)

```bash
# 1. Infra
docker compose up -d            # Postgres pgvector pe portul host 5434
alembic upgrade head            # include migrația 004 (sessions + chat_messages)

# 2. Date
docker exec -i ai-orchestrator-postgres-1 pg_restore -U demo -d rag_demo --data-only < data/rag_demo.dump
# (alternativ: python scripts/seed_tables.py && python scripts/seed_chunks.py)

# 3. Dependențe
pip install -r requirements.txt
pip install -e skillab-py

# 4. .env (chei necesare)
#   GEMINI_API_KEY=...                  # agenții L5/L6 (RAG, Analyst)
#   ANTHROPIC_API_KEY=...               # memory + caching + intent (Claude)
#   ANTHROPIC_MODEL=claude-haiku-4-5
#   DATABASE_URL=postgresql://demo:demo123@localhost:5434/rag_demo

# 5. Antrenează clasificatorul de intenții (produce data/intent/intent_classifier.joblib)
python scripts/train_intent.py
```

### Comenzi (din rădăcina repo-ului)

| Comandă | Ce demonstrează |
|---|---|
| `python src/main.py` | RAG + Analyst de bază (L5/L6, pe Gemini) |
| `python scripts/smoke_memory.py` | **Task 1** — conversație multi-turn + persistență după restart (Postgres) |
| `python scripts/smoke_prompt_cache.py` | **Task 2** — `cache_creation` → `cache_read`, tokens economisiți + latență |
| `python scripts/compare_intent.py` | **Task 3** — tabel clasificator-vs-LLM (latență / cost / acuratețe) |

> **Notă quota Gemini:** free tier ≈ 20 cereri/zi/model. `python src/main.py` plus bucla evaluate/refine a orchestratorului o consumă rapid; cele trei demo-uri L8 rulează pe Claude (Anthropic), deci quota Gemini contează doar pentru `main.py`.

## Temă L10 — MCP & Guardrails — cum se testează

Cei doi agenți sunt expuși ca tool-uri într-un singur server MCP (`src/mcp_server.py`, transport STDIO), iar intrarea în server este protejată de guardrails (`src/guardrails.py`).

- **Task 1** — `AnalystAgent` expus ca tool MCP `data_analyst` (`AnalystAgent.chat(question)`).
- **Task 2** — `Orchestrator` expus ca al doilea tool MCP `document_qa` în **același** server (`Orchestrator.run(query, session_id)`), plus integrare în **Claude Code** prin `.mcp.json`.
- **Task 3** — guardrail de intrare: validare structurală (tip, dimensiune, câmpuri permise) + detecție prompt-injection (regex, opțional LLM-as-Judge) care **blochează** inputul periculos **înainte** să ajungă la agent.

### Setup (o singură dată)

```bash
docker compose up -d            # Postgres pgvector pe portul host 5434
alembic upgrade head
docker exec -i ai-orchestrator-postgres-1 pg_restore -U demo -d rag_demo --data-only < data/rag_demo.dump

pip install -r requirements.txt   # include mcp (SDK-ul oficial MCP)
pip install -e skillab-py

# .env (chei necesare):
#   ANTHROPIC_API_KEY=...
#   ANTHROPIC_MODEL=claude-haiku-4-5
#   DATABASE_URL=postgresql://demo:demo123@localhost:5434/rag_demo
```

### Client Python (smoke test)

```bash
python scripts/smoke_mcp.py
```

Parcurge tot ciclul JSON-RPC: `initialize` → `tools/list` (2 tool-uri) → `tools/call`. Demonstrează:
- apelurile curate răspund (`isError=False`);
- promptul de injection (`document_qa`) e blocat de guardrail → `isError=True`, text `Blocked by guardrail (regex)`;
- inputul cu tip greșit (`{"question": 123}`) și cu câmp necunoscut (`{"question":"x","evil":"y"}`) sunt blocate de validarea `inputSchema` a SDK-ului → `isError=True`, text `Input validation error: …`.

> **Două straturi de apărare.** SDK-ul `mcp` validează `inputSchema` (tip, dimensiune, câmpuri) **înainte** de handler, deci prinde atacurile structurale; `src/guardrails.py` prinde ce trece de schemă (prompt-injection, semantic). În ambele cazuri agentul **nu rulează** pentru un input blocat. Blocările apar ca `CallToolResult` cu `isError=True` (eroare de execuție tool), nu ca un cod JSON-RPC `-32xxx` — în versiunea instalată a SDK-ului orice excepție din handler e împachetată în `isError`.

### Claude Code

`.mcp.json` din rădăcina repo-ului înregistrează serverul STDIO. În Claude Code:

```
/mcp            # listează „ai-orchestrator · connected · 2 tools"
```

Apoi invocă fiecare tool (`data_analyst`, `document_qa`) și confirmă că răspund.

> **Igienă stdout.** Pe STDIO, stdout transportă **doar** JSON-RPC, iar logurile merg pe stderr. Serverul rulează agenții forțat pe **Anthropic**, fiindcă providerul Google scrie accidental pe stdout (`print`) și ar corupe stream-ul protocolului.

## Structură

```
├── alembic/           # Migrații DB
├── data/              # CSV-uri, documente
├── prompts/           # YAML prompts
├── scripts/           # Seed scripts
├── skillab-py/        # LLM, prompts, tools
│   └── src/skillab/tools/
│       ├── implementations.py  # join_data, filter_data
│       └── params.py           # Pydantic params
└── src/
    ├── database.py        # Connection + transaction
    ├── models.py          # SQLAlchemy models
    ├── repositories.py    # Repository pattern
    ├── rag_service.py     # pgvector search service
    ├── state.py           # Pydantic states
    ├── rag_agent.py       # node_refine
    ├── orchestrator.py    # node_evaluate, node_answer
    ├── nl2sql_agent.py    # node_generate_sql, node_validate_sql, node_execute_sql
    ├── analyst_agent.py   # node_make_plan, node_synthesize
    └── main.py
```

## Componente implementate

Toate nodurile și tool-urile de mai jos sunt implementate și funcționale.

### 1. RAG Agent (`src/rag_agent.py`)
```python
def node_refine(self, state: RAGAgentState) -> dict:
    """
    Dacă state.feedback există:
    1. Renderează prompt "rag_refine"
    2. Apelează LLM
    3. Parsează JSON în RefinedQuery.model_validate_json()
    4. Return {"refined": refined_query}

    Dacă nu există feedback:
    - Return {"refined": RefinedQuery(query=state.query)}
    """
```

### 2. Orchestrator (`src/orchestrator.py`)
```python
def node_evaluate(self, state: OrchestratorState) -> dict:
    """
    1. Construiește context din state.rag_result.results
    2. Renderează prompt "rag_evaluate"
    3. Apelează LLM
    4. Parsează în OrchestratorFeedback.model_validate_json()
    5. Return {"feedback": feedback}
    """

def node_answer(self, state: OrchestratorState) -> dict:
    """
    1. Construiește context din state.rag_result.results
    2. Renderează prompt "rag_answer"
    3. Apelează LLM
    4. Return {"answer": answer, "status": "success"|"partial"|"failed"}
    """
```

### 3. NL2SQL Agent (`src/nl2sql_agent.py`)
```python
def node_generate_sql(self, state) -> dict:
    # Generează SQL din întrebare

def node_validate_sql(self, state) -> dict:
    # Validează SQL (sqlparse)

def node_execute_sql(self, state) -> dict:
    # Execută SQL, returnează DataFrame
```

### 4. Analyst Agent (`src/analyst_agent.py`)
```python
def node_make_plan(self, state) -> dict:
    # Creează plan cu QueryStep și ToolStep

def node_synthesize(self, state) -> dict:
    # Sintetizează răspuns din state.slices
```

### 5. Tools (`skillab-py/src/skillab/tools/implementations.py`)
```python
@register_tool
def join_data(params: JoinDataParams) -> pd.DataFrame:
    # pd.merge(params.input_dfs[0], params.input_dfs[1], ...)

@register_tool
def filter_data(params: FilterDataParams) -> pd.DataFrame:
    # params.input_dfs[0][mask]
```

## Plan format

LLM generează plan JSON:
```json
[
  {"id": "q1", "action": "query", "table": "achizitii", "sub_question": "..."},
  {"id": "q2", "action": "query", "table": "anunturi", "sub_question": "..."},
  {"id": "joined", "action": "tool", "tool_name": "join_data", "input_steps": ["q1", "q2"], "params": {"left_key": "cui", "right_key": "cui"}},
  {"id": "result", "action": "tool", "tool_name": "filter_data", "input_steps": ["joined"], "params": {"column": "valoare", "operator": ">", "value": "50000"}}
]
```

Rezultate în `state.slices["q1"]`, `state.slices["joined"]`, etc.

## Hints

```python
# Render prompt
prompt = self.prompts.render("rag_evaluate", query=q, context=ctx, ...)

# LLM call
response = self.llm.generate_sync([{"role": "user", "content": prompt}])

# Parse JSON direct în Pydantic (recomandat)
import re
match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
json_str = match.group(1) if match else response
feedback = OrchestratorFeedback.model_validate_json(json_str)

# SQL execution
with transaction() as session:
    result = session.execute(text(sql_query))
    df = pd.DataFrame(result.mappings().all())

# Tool catalog pentru prompt
tools_catalog = ToolWrapper.to_prompt_string()
```

## Run

```bash
cd src && python main.py
```
