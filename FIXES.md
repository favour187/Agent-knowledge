# Fixes Applied

This repo's adapter (LoRA/QLoRA) training pipeline previously failed on every
run — 11 prior attempts in `adapters*/` all ended with `"status": "failed"`
and no usable adapter. Those failed-run directories have been removed. The
following bugs were found (by actually installing torch/transformers/peft/
datasets and running the pipeline end-to-end against a tiny local model
until it succeeded) and fixed:

1. **`requirements-training.txt` was uninstallable.**
   `fused-layers` and `megatron-lm` don't exist on PyPI, and `bleu>=1.0.0` is
   an impossible constraint (max release is 0.3). `apex` resolved to an
   unrelated ancient package, not NVIDIA's. Split into:
   - `requirements-training.txt` — core set, verified to resolve cleanly.
   - `requirements-training-extra.txt` — optional heavy stuff (deepspeed,
     wandb, mlflow, trl, ONNX/GGUF export, dev tooling).
   Also added `structlog`, which every module in `core/training/` imports
   but which was missing from the file entirely.

2. **`core/training/trainer.py`: broken data collator.**
   Imported `transformers.DataCollator`, which is a typing protocol, not an
   instantiable class. This was the exact cause of the
   `'Callable() takes no arguments'` failures. Fixed to use the working
   custom `DataCollator` in `core/training/dataset.py` (was defined, but
   never actually used anywhere).

3. **`core/training/trainer.py`: CPU training always crashed.**
   `fp16=not torch.cuda.is_available()` forced fp16 on CPU, which PyTorch
   doesn't support for training. Mixed precision is now only enabled on GPU.

4. **`core/training/trainer.py`: wrong default LoRA target modules.**
   Defaulted to `["q_proj", "v_proj"]` (Llama-style), but GPT-2 uses
   `c_attn`/`c_proj`, so training on GPT-2 without an explicit override threw
   `"Target modules {...} not found in the base model"`. Default fixed;
   docstring added noting the override needed for Llama/Mistral/Phi.

5. **`core/training/pretrain.py`: `NameError: text_column`.**
   `.json`-suffixed data files hit a branch referencing an undefined
   `text_column` variable. Also fixed a file-pointer bug where `f.read()`
   consumed the file before a later `json.load(f)` tried to read it again.

6. **`core/training/pretrain.py`: instruction-format data never got a `text`
   field.** The pipeline detected `{"instruction": ..., "response": ...}`
   data and logged "detected_instruction_format" but never converted it,
   so tokenization later crashed with `KeyError: 'text'`. Now builds a
   proper instruction/response prompt into a `text` column (mirrors the
   already-working chat-format conversion just above it).

7. **`core/training/loRA.py`: broken memory calculator.**
   `model_size_gb = model_size_b * bytes_per_param["fp32"] / 1e9 * 1e9 / 1e9`
   had a redundant `/1e9`, zeroing out the model size and cascading into
   nonsense numbers for gradients/optimizer states/recommendations in the
   `info` CLI command. Rewritten with a clear fp32-baseline vs
   requested-precision split.

8. **`core/training/adapters.py`: `AdapterManager.train_adapter` returned the
   wrong path.** It pointed callers at `output_path` directly (which only
   ever contains `adapter_info.json`), when the actual trained adapter
   weights are written to `output_path/<run_name>/export/hf/`. Calling
   `load_adapter()` on the returned path would fail with a missing
   `adapter_config.json`. Fixed to return the real export path (there was
   dead code — `... if False else ...` — showing this had been half-fixed
   and abandoned previously).

9. **`core/training/scripts/run_finetune.sh`: incorrect final usage hint.**
   Printed a `load_adapter('$OUTPUT/adapter_info.json')` example that was
   wrong on two counts (wrong file, wrong directory level). Fixed to point
   at the real nested export path.

10. **`pyproject.toml` / `README.md`: `pytest --cov=arena`.**
    The package is `core/`, not `arena` — coverage silently collected
    nothing. Fixed to `--cov=core`.

## Verified working (not just reviewed)

Ran the actual pipeline (`core/training/cli.py train`, `AdapterManager.
train_adapter`, and `run_finetune.sh`) against a small locally-built GPT-2
model (no network/HF Hub access needed to verify) for:

- Plain-text format (`data/sample_train.jsonl`) — trains, exports ✅
- Instruction format (`data/sample_instruction.json`) — trains, exports ✅
- Chat format (`data/sample_chat.jsonl`) — trains, exports ✅
- `--dry-run` — validates without training ✅
- `AdapterManager.train_adapter` → `load_adapter` → `merge_adapter` →
  `compare_adapters` full lifecycle ✅
- `core.training.cli info` — now shows sane, non-zero memory estimates ✅
- `pytest tests/` — all 10 existing tests pass, coverage now reports against
  `core/` correctly ✅

## What to do with a real model

Everything above was verified against a tiny local model (2 layers, 32-dim)
since this environment has no access to huggingface.co to download real
weights. The code paths are identical for real models — just point
`--model` at `gpt2`, `meta-llama/Llama-2-7b-hf`, etc. For non-GPT-2 models,
remember to override `--lora-target-modules`-equivalent (`lora_target_modules`
in code) to `q_proj`/`v_proj` (Llama/Mistral) since the new default is
GPT-2-specific.

---

# Backend / API / Database fixes (second session)

The API layer (`api/`) did not import at all before this pass — it crashed
on the very first import. Beyond that, every route returned hardcoded fake
data with no real database behind it, despite `requirements.txt` listing
`sqlalchemy`/`asyncpg` and a full schema existing in
`database/migrations/001_initial_schema.sql`.

## Bugs fixed

1. **Missing `api/routes/auth.py`.** `api/main.py` and
   `api/routes/__init__.py` both imported it; it didn't exist. The whole API
   crashed on import before this.
2. **Wrong import path for AI providers.** `api/main.py` imported
   `OpenAIProvider`/`AnthropicProvider` from `core.ai_runtime.engine`; they
   actually live in `core.ai_runtime.providers.openai` /
   `core.ai_runtime.providers.anthropic`.
3. **`core/ai_runtime/providers/openai.py` imported type names that don't
   exist in any real published `openai` SDK version**
   (`ChatCompletionAssistantToolCall`, `ChatCompletionToolMessage`,
   `ChatCompletionMessageToolCallChunk`, `ChatCompletionTool`) — looks like
   this was written without ever running against the real library. Fixed to
   use real types (`ChatCompletionMessageFunctionToolCall`) or plain dicts
   where a TypedDict was being over-relied on.
4. **`passlib[bcrypt]` is broken with modern bcrypt** (confirmed by actually
   running it: `AttributeError: module 'bcrypt' has no attribute
   '__about__'`, then a `ValueError` on hash). passlib has been unmaintained
   since ~2020. Replaced with direct `bcrypt` usage (`api/auth_utils.py`).
5. **No database layer existed at all.** `sqlalchemy`/`asyncpg` were listed
   in `requirements.txt` but nothing in the codebase imported them. Added:
   - `database/db.py` — async engine/session (defaults to a zero-config
     local SQLite file via `aiosqlite`; set `DATABASE_URL` to a real
     Postgres DSN, e.g. `postgresql+asyncpg://user:pass@host/db`, for
     production).
   - `database/models.py` — SQLAlchemy models for the tables the API routes
     actually use: `users`, `agents`, `tasks`, `memories`,
     `knowledge_entities`, `knowledge_relations`, `sessions`, `messages`,
     `tool_executions`.
6. **Every route was a hardcoded stub.** Rewrote all of `auth.py`,
   `agents.py`, `tasks.py`, `memory.py`, `knowledge.py`, `sessions.py`,
   `tools.py` to do real CRUD against the database instead of returning
   fixed placeholder responses. Added real bcrypt password hashing + JWT
   bearer tokens (`api/auth_utils.py`) for `/api/auth/register`,
   `/login`, `/me`.
7. **`ToolRegistry._register_builtin_tools()` was a no-op** (`pass`) — the
   app always started with zero tools, even though `tools/filesystem.py`
   and `tools/web_search.py` are real, working implementations. Wired both
   in via a small adapter, so `app_state.tool_registry` now actually has
   tools, and `POST /api/tools/execute` genuinely executes them (verified:
   wrote and read back a real file through the API) and records real rows
   in `tool_executions`.
8. **Fixed a `Pydantic` field-shadowing warning** in the tools response
   model (`schema` shadows a `BaseModel` attribute) by renaming to
   `tool_schema`.
9. **Circular import risk**: `AppState`/`app_state` used to live inline in
   `api/main.py`, which imports the route modules — so a route module
   couldn't import `app_state` back from `api/main.py`. Moved into its own
   `api/state.py` so routes (like the new `tools.py`) can use it directly.
10. **Nothing initialized the database.** Added an `init_db()` call
    (creates tables if missing) to the FastAPI `startup()` lifecycle.

## Verified working (not just reviewed)

Started the real server (`uvicorn api.main:app`) and hit every route with
real HTTP requests, confirming real persistence in SQLite (`arena.db`):
register → login → `/me` with a real JWT ✅; create/list agents ✅;
create/update tasks ✅; add/search memory ✅; create entities + a relation
between them ✅; list tools (2 real ones, not the old 2 fake ones) ✅;
execute the `filesystem` tool for real (wrote then read back a file) and
confirmed it was logged in `/api/tools/executions` ✅; create a session,
post a message, list messages back ✅.

## Known gaps — still true, not addressed in this pass

- **`agents.py`'s `send_message`** persists the session/messages but does
  **not** call through to `AIRuntime`/`AgentManager` for a real model
  response yet — it returns a fixed placeholder assistant reply. Wiring
  this up is the natural next step if you want `/api/agents/{id}/message`
  to actually talk to GPT-4/Claude.
- **Memory search is plain SQL substring matching**, not real vector
  similarity. The schema has real `VECTOR(1536)` columns designed for
  pgvector cosine similarity in Postgres; nothing generates real embeddings
  yet, and the SQLite dev path stores embeddings as JSON, not a vector
  type.
- **`frontend/` is just a `package.json`** — no actual React components,
  pages, or app code exist yet.
- **Tables with no API routes at all**: `api_keys`, `plans`, `plan_steps`,
  `audit_logs`, `feedback`, `evaluation_results`, `learned_patterns`. These
  exist in the SQL migration and are presumably meant to back
  `core/planning_engine`, `core/self_evaluation`, `core/self_improvement`,
  but nothing in `api/routes/` exposes them over HTTP yet.
- **Production Postgres + pgvector**: the SQLite dev path (default,
  zero-config) does not exercise the real `VECTOR`/`ivfflat` bits of
  `database/migrations/001_initial_schema.sql`. For a real deployment, run
  that SQL migration directly against Postgres rather than relying on
  `init_db()`'s `create_all()` (which only creates plain-equivalent
  tables), and switch `DATABASE_URL` to `postgresql+asyncpg://...`.

---

# Third session

This environment still has no network access (no `pip install`, no
`huggingface.co`, no live OpenAI/Anthropic API calls), so everything below
was verified by exhaustive static review and `python3 -m py_compile` across
every `.py` file in the repo, not by actually running `uvicorn`/`pytest`
against real `fastapi`/`sqlalchemy` installs the way the first two sessions
did. Treat this pass as thorough code review + targeted fixes, not
execution-verified like the earlier entries.

## Bugs fixed

1. **Critical: `AIRuntime.register_provider` key mismatch**
   (`core/ai_runtime/engine.py`). It stored providers under
   `provider.__class__.__name__.lower()` (e.g. `"openaiprovider"`), but
   `complete()`/`stream()` looked providers up by `config.provider.value`
   (e.g. `"openai"`). These never matched, so **every real AI completion
   silently failed** with `ValueError: No provider registered for ...`,
   even with a valid `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` configured and
   the provider "registered" at startup. This was true from the very first
   session onward and was never caught because nothing in this environment
   can make a real network call to OpenAI/Anthropic to notice. Fixed by
   changing `register_provider(provider)` to `register_provider(provider_type,
   provider)`, keyed on the `ModelProvider` enum; updated both call sites
   in `api/main.py`.
2. **`api/routes/agents.py`'s `send_message`** was a hardcoded echo
   placeholder (documented as a known gap in the second session). Wired to
   the shared `app_state.ai_runtime`, using the agent's
   `system_prompt`/`model`/`temperature`/`max_tokens`. Falls back to a
   clear, non-crashing message if no provider is configured or the call
   fails, rather than a fake reply presented as real.
3. **`api/routes/memory.py`'s `consolidate_memories`** only counted
   low-importance rows without changing anything (documented as a stub in
   the second session). Replaced with real decay-and-forget logic mirroring
   `core.memory_manager.manager.MemoryManager`'s forgetting curve, applied
   directly against the DB-backed `memories` table.
4. **7 tables existed in `database/migrations/001_initial_schema.sql` with
   no ORM models and no API routes**: `api_keys`, `plans`, `plan_steps`,
   `audit_logs`, `feedback`, `evaluation_results`, `learned_patterns`
   (explicitly called out as a known gap in the second session). Added:
   - SQLAlchemy models for all 7 in `database/models.py`.
   - `api/routes/plans.py` — plans + nested plan_steps CRUD.
   - `api/routes/evaluation.py` — persists real
     `core.self_evaluation.evaluator.SelfEvaluator` runs (`POST /run`),
     plus list/get.
   - `api/routes/feedback.py` — record/list/get feedback.
   - `api/routes/patterns.py` — upsert/list/get/delete learned patterns.
   - `api/routes/audit.py` — read-only list/get, plus a `log_audit_event()`
     helper other routes can call.
   - `api/routes/api_keys.py` — issue/list/revoke API keys for the current
     user; raw key is bcrypt-hashed at rest and shown only once, at
     creation.
   - Wired `log_audit_event()` into `auth.py`'s `register`/`login`.
   - Registered all 6 new routers in `api/main.py` and
     `api/routes/__init__.py`.
5. **`api/main.py`: registered the `SelfEvaluator`'s built-in `coding`
   rubric at startup** (previously only `default` was registered, so
   `Rubric.coding()` existed in code but was permanently unreachable via
   `SelfEvaluator.get_rubric()`).
6. Minor: `api/routes/plans.py`'s step-update endpoint originally mixed
   implicit query params (`step_status: str`, `error: Optional[str]`) with
   an implicit body param (`result: Optional[dict]`) in the same signature
   — technically works in FastAPI but is a confusing, inconsistent request
   shape compared to every other route in the codebase. Replaced with a
   proper `PlanStepUpdate` Pydantic body model.

## Verified (static only — see caveat above)

- `python3 -m py_compile` on every `.py` file in the repo: clean, no
  syntax errors.
- Manually cross-checked every new/edited route function's field names and
  method signatures against the actual `database/models.py` columns and
  `core/self_evaluation/evaluator.py`'s `SelfEvaluator.evaluate()`/
  `Rubric` API (the first draft of `evaluation.py` passed a `rubric_name`
  string where `evaluate()` expects a resolved `Rubric` object — caught and
  fixed before this was ever run).
- Confirmed no other call sites of `AIRuntime.register_provider` exist
  elsewhere in the repo (tests, scripts, etc.) that the signature change
  would break.

## Known gaps — still true, not addressed in this pass

- **No `fastapi`/`sqlalchemy`/`pydantic`/`torch`/etc. available in this
  environment and no network to install them** — unlike the first two
  sessions, none of this session's changes were exercised against the real
  libraries or a live server. Recommend running `pytest tests/ -v` and
  actually hitting `/api/plans`, `/api/evaluation/run`,
  `/api/agents/{id}/message`, etc. with real HTTP requests in an
  environment with network access before treating this session's changes
  as verified the way the first two were.
- **Real vector/embedding-based semantic search** (`memory.py`'s and
  `knowledge.py`'s search endpoints still do plain SQL substring
  matching): still not wired up. This needs either a real embeddings API
  call (network-dependent) or a deliberate choice of an offline embedding
  model — a design decision better made with input from whoever's
  deploying this, not silently substituted in.
- **`frontend/` is still just a `package.json`** — no React app exists.
  Building one from scratch is a substantial, opinionated project in its
  own right (routing, state management, design system, per-endpoint pages
  for the now much larger API surface) and wasn't attempted here.
- **`core.memory_manager.manager.MemoryManager` (in-process) and the
  DB-backed `memories` table are still two separate, unconnected memory
  systems** — `api/routes/memory.py` talks only to the DB; the in-process
  manager instantiated in `api/main.py`'s `startup()` is otherwise unused
  by any route. Unifying them is a real architectural decision (e.g.
  should the in-process manager be the source of truth with the DB as
  persistence, or vice versa?) rather than a bug fix.
- Same Postgres/pgvector caveat as the second session: `init_db()`'s
  `create_all()` only creates plain-equivalent columns for the new tables
  too; a real deployment should still run the `.sql` migration directly.

