# CLAUDE.md — Permanent Operating Manual

This file is the operating manual for this repository. It is written so that any
future engineer or AI model — regardless of capability — can work on this project
without eroding the design. Read it fully before changing anything.

**The full knowledge base lives in `docs/`. This file is the entry point and index.**

| Document | Read it when |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Before changing pipeline flow, agents, or state |
| [docs/DESIGN_DECISIONS.md](docs/DESIGN_DECISIONS.md) | Before questioning "why is it built this way?" |
| [docs/ENGINEERING_PRINCIPLES.md](docs/ENGINEERING_PRINCIPLES.md) | Before writing any new code or prompt |
| [docs/PROMPT_PHILOSOPHY.md](docs/PROMPT_PHILOSOPHY.md) | Before editing any prompt |
| [docs/KNOWN_FAILURE_MODES.md](docs/KNOWN_FAILURE_MODES.md) | When debugging anything |
| [docs/TESTING_GUIDE.md](docs/TESTING_GUIDE.md) | Before and after any change |
| [docs/FUTURE_ROADMAP.md](docs/FUTURE_ROADMAP.md) | Before adding features |
| [docs/MODEL_MIGRATION.md](docs/MODEL_MIGRATION.md) | Before replacing Gemini |
| [docs/PROJECT_HISTORY.md](docs/PROJECT_HISTORY.md) | To understand how we got here |
| [docs/REPO_AUDIT.md](docs/REPO_AUDIT.md) | To know what is stale, dead, or risky right now |
| [docs/ENGINEERING_HANDOVER.md](docs/ENGINEERING_HANDOVER.md) | Original internship handover (narrative source of truth) |
| [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md) | Business context and output contract |
| [docs/PYTHON_TO_JAVA_MIGRATION.md](docs/PYTHON_TO_JAVA_MIGRATION.md) | Porting to Java (note: describes the *committed* state, one iteration behind the working tree) |

---

## 1. What This Project Actually Is

A pipeline that converts a **CAD-style 2D structural section drawing** (an image:
I-beam, U-section, T-section, compound shapes…) into **deterministic,
machine-readable geometry JSON**: corner coordinates, boundary line segments,
rectangular structural components, and joint locations marked by red lines on the
drawing.

It is **not** an image classifier. Recognizing "this is an I-beam" is worthless
downstream. The product is the *coordinate model* — exact enough that centroid,
moment of inertia, and joint design can be computed from it. Wrong geometry that
looks plausible is worse than no geometry, so the system's core value is
**honesty**: it must report what it cannot determine instead of guessing.

**Stack:** FastAPI backend (`backend/`), LangGraph pipeline of 4 Gemini 2.5 Flash
calls, deterministic Python gates (shapely + union-find), Next.js frontend
(`frontend/`). Single endpoint: `POST /api/analyze` (multipart image → JSON +
Excel/DXF exports).

## 2. Project Goals (in priority order)

1. Accurate geometry reconstruction from explicit dimensions only.
2. Zero hidden assumptions — every assumption is surfaced or eliminated.
3. Detection of under-constrained drawings (report, never invent).
4. Correct component decomposition (rectangles tiling the section).
5. Robust joint detection (red markers) that can never harm geometry.
6. Interpretable frontend visualization.
7. Foundation for downstream engineering calculation.

## 3. Engineering Philosophy (condensed — full version in docs/ENGINEERING_PRINCIPLES.md)

- **The system is a deterministic geometry calculator that happens to use an LLM
  for perception** — not an LLM that produces geometry.
- Geometry may come ONLY from (a) explicit dimensions, (b) arithmetic on explicit
  dimensions. Never from symmetry, centering, drafting convention, or "it looks
  aligned."
- **LLMs perceive; code verifies.** Every LLM output passes through deterministic
  gates (Pydantic schemas, `geometry/validity.py`, `geometry/determinacy.py`).
- **One agent = one responsibility.** Every regression in this project's history
  came from letting two concerns share a channel.
- **Enforce boundaries structurally, not by instruction.** "Please ignore X" in a
  prompt is weak; making X physically absent from the agent's input is strong.
- **Honesty beats coverage.** "I cannot determine this" is a correct, valuable
  answer.

## 4. Repository Navigation

```
backend/
  main.py                    FastAPI app: POST /api/analyze, GET /api/health
  pipeline.py                LangGraph wiring — THE architecture lives here
  schemas.py                 Pydantic contracts for every agent (the real API between stages)
  exporters.py               Excel (openpyxl) + DXF (ezdxf) generation
  agents/
    gemini_caller.py         Single Gemini REST client: retries, timeouts, token diagnostics
    observer.py              Agent 1 — perception only, hard-fails on schema error
    inferencer.py            Agent 2 — geometry arithmetic, feeds the retry loop
    validator.py             Agent 3 — audit, runs only for "complex" sections
    joint_placement.py       Agent 2b — red-marker detection, runs AFTER frozen geometry, never raises
  prompts/
    observer_prompt.py       Static prompt (joint-blind by design)
    inferencer_prompt.py     Template; embeds observation JSON
    validator_prompt.py      Template; embeds inference JSON, strips "joints" key
    joint_prompt.py          Template; embeds frozen geometry as reference frame only
  geometry/
    validity.py              LIVE: assumptions → invalid gate + shapely tiling checks
    determinacy.py           LIVE (warning-only): union-find axis-spanning determinacy check
    render.py                DEAD CODE (not imported by pipeline) — shapely-union geometry rebuild + matplotlib render; kept as design reference for the known line_segments bug fix
    finalize.py              DEAD CODE — never called; references a field that no longer exists
  debug/                     Captured real Gemini outputs from a regression session (fixtures)
frontend/                    Next.js: upload → canvas diagram + tables + downloads
docs/                        All knowledge documents (see index above)
docs/images/, docs/debug_cases/   Test drawings (the de-facto regression suite)
```

**Environment:** `backend/.env` needs `GEMINI_API_KEY` (from Google AI Studio).
Model URL is hardcoded in `gemini_caller.py` (`gemini-2.5-flash`). Frontend needs
`NEXT_PUBLIC_API_URL`. Run backend: `uvicorn main:app --reload --port 8000` from
`backend/` with venv active. Run frontend: `npm run dev` from `frontend/`.

## 5. Architecture Overview (details in docs/ARCHITECTURE.md)

```
Image ─→ Observer ─→ Inferencer ─→ [Pydantic gate] ─┬─ simple → ────────────┐
                          ↑                          ├─ complex → Validator ─┤
                          └──── retry (max 1) ───────┴──── invalid ──────────┘
                                                                             │
                                              GEOMETRY FROZEN ───────────────┤
                                                                             ▼
                                                                     Joint Placement
                                                                             ▼
                                          build_output: assess_validity (blanks geometry
                                          if assumptions exist) + check_determinacy
                                          (warning-only) → final JSON
```

- Observer: reports only what is literally visible. No arithmetic, no joints.
- Inferencer: derives geometry by arithmetic only; declares `assumptions` for
  anything it can't derive. Only agent in the retry loop's target.
- Validator: audits geometry vs image; only for `complexity == "complex"`; its
  errors can trigger the single retry; may return `corrected_corners`.
- Joint Placement: detects red marker lines **directly from the image pixels**,
  using frozen geometry only as a coordinate reference frame. No retry edge.
  Never raises — degrades to `joints: []` + warning.

## 6. Invariants — Things That Must NEVER Break

These are load-bearing. Each one exists because its violation caused a real
regression (see docs/PROJECT_HISTORY.md and docs/DESIGN_DECISIONS.md).

1. **No joint data may ever reach Observer, Inferencer, or Validator.** Enforced
   at three layers today: (a) `ObserverOutput` has no joint fields at all;
   (b) the graph has no edge from `place_joints` back into
   `infer`/`validate`/`retry`; (c) `build_validator_prompt` strips `"joints"`
   from its input dict. Weakening ANY layer reopens the geometry-corruption
   regression of Phase 3.
2. **Joint Placement never raises and never mutates
   corners/components/line_segments.** Its failure cost is capped at "no joints
   for this drawing."
3. **`JointPlacementOutput` must have no corners/components fields.** The schema
   is the type-level proof that joints can't feed back into geometry.
4. **A joint problem must never trigger a geometry retry.** The retry loop is
   geometry-only.
5. **Geometry only from explicit dimensions + arithmetic.** The Inferencer prompt
   must never regain a symmetry/centering "derivation" rule.
6. **Non-empty `assumptions` ⇒ geometry blanked** (`assess_validity`), with a
   human-readable reason naming the missing dimension. The LLM never decides
   valid/invalid; deterministic code does.
7. **Origin rule:** min x = 0, min y = 0, no negative coordinates. Frontend,
   exporters, and validator all rely on it.
8. **`unit` is `"unspecified"` when absent — never guessed.** Do not default to mm.
9. **Observer schema failure is a hard stop** (raise), not a soft pass-through.
   Passing unvalidated observation downstream is "retry-by-corruption."
10. **Validator returning garbage is treated as `valid: true`** — otherwise the
    pipeline can loop forever on a broken auditor.
11. **`temperature=0` and `responseMimeType: application/json`** on every Gemini
    call.
12. **Timeouts are not retried; only HTTP 503/429 are** (max 3, parsed backoff).
    Read timeout is 300s because complex drawings legitimately generate for
    minutes — do not "clean up" the asymmetric `httpx.Timeout` back to one number.
13. **Frontend response contract:** `{section_type, unit, dimensions_read,
    corners, line_segments, components, joints, warnings}` — `assumptions` and
    `inference_chain` are internal and never serialized to the API response.

## 7. Typical Development Workflow

1. Pick a test image from `docs/images/` (drawio synthetics) or
   `docs/debug_cases/` (real/official drawings, red-marker cases).
2. Run backend, `curl -F "file=@docs/images/test_c.png;type=image/png"
   http://localhost:8000/api/analyze`.
3. Read the `[stage:...]` and `[gemini]` log lines — they are the observability
   system: per-stage timing, token counts, finish_reason, routing decisions,
   validity/determinacy verdicts.
4. **Run each image at least twice.** Gemini is non-deterministic even at
   temperature 0; one good run proves nothing (see docs/TESTING_GUIDE.md).
5. Compare against a pre-change run of the same images. Geometry (corners,
   components) must be bit-identical in intent; joints may vary slightly.

## 8. How to Safely Modify the Project

- **Changing a prompt:** read docs/PROMPT_PHILOSOPHY.md first. Every sentence in
  the prompts exists to *prevent* a specific observed failure; deleting a
  "redundant-looking" rule usually reintroduces it. Keep the JSON example in the
  prompt exactly in sync with the Pydantic schema field names — a mismatch is a
  guaranteed schema-validation failure at runtime.
- **Changing a schema:** schemas are the inter-agent contract. Update in
  lockstep: schema field ↔ prompt JSON example ↔ any consumer
  (`pipeline.build_output`, `determinacy.check_determinacy` reads
  `observation["dimensions"]`, exporters, frontend). Prefer adding optional
  fields with defaults; never rename without grepping all consumers.
- **Adding an agent:** see rules below.
- **Touching the retry/timeout logic:** read docs/KNOWN_FAILURE_MODES.md §API
  instability first. The current semantics encode hard-won distinctions
  (transient vs terminal, slow-generation vs dead-network).
- After ANY change: re-run the image set per docs/TESTING_GUIDE.md.

## 9. Common Mistakes (all have actually happened or been narrowly avoided)

- Letting joint information "helpfully" flow into geometry stages → geometry
  regressed (U-section decomposed into 5–6 components instead of 3).
- Relying on a prose "ignore this" instruction instead of physically withholding
  data → joint-locator dimensions laundered through arithmetic into fake corners
  (see `backend/debug/inferencer_output.json`, key `X_J2`).
- Treating one successful run as validation → non-determinism bites later.
- Editing a prompt's JSON example without updating `schemas.py` (or vice versa).
- "Simplifying" the two-list dimension design or observer rules that look
  paranoid — the paranoia is the fix.
- Assuming `docs/FRONTEND_API_CONTRACT.md` or `README.md` are current — both are
  stale (see docs/REPO_AUDIT.md).
- Retrying timeouts or hard quota errors → hours of blocked development.
- Trusting the model's own "valid" self-assessment instead of the deterministic
  gates.

## 10. Rules for Adding Future Agents

1. One responsibility per agent. If you can't state it in one sentence, split it.
2. Decide up front: can this agent's failure be allowed to kill the run?
   Perception (Observer) → yes, hard-fail. Annotation (Joint Placement) → no,
   degrade gracefully, never raise.
3. New agents that *annotate* geometry must run **after** the geometry retry
   loop, receive geometry read-only, have an output schema with no geometry
   fields, and have no edge back into the loop. Copy the `place_joints` pattern.
4. New agents that *contribute to* geometry must live inside the retry loop and
   be covered by the deterministic gates.
5. Give it a Pydantic output schema, a `[stage:name:*]` log prefix, and an
   `agent_name` for `call_gemini` diagnostics.
6. Route through `agents/gemini_caller.py` — never add a second HTTP client with
   different retry/timeout semantics.

## 11. Rules for Changing Prompts

1. Prompts are specifications, not suggestions. Treat each edit as a contract
   change.
2. Never add a capability to a prompt that the schema can't represent, or
   vice versa.
3. Never tell the Observer or Inferencer anything about joints beyond "red
   marker lines are annotations; mentally erase them."
4. Never reintroduce symmetry/centering as a *derivation* in the Inferencer
   prompt. The worked asymmetric-I-beam example exists precisely to teach the
   arithmetic-vs-assumption boundary; keep it.
5. Prompt examples must show the origin rule, clockwise-from-top-left labeling,
   and `"assumptions": []` for fully-dimensioned drawings.
6. Any new "do not" rule should cite (in the .py docstring, not the prompt) the
   failure it prevents, so future editors don't delete it as noise.

## 12. Rules for Changing Schemas

1. `schemas.py` is the single source of truth for inter-agent data shape.
2. The `InferencerOutput.geometry_constraints` validator must keep its
   `if self.assumptions: return self` early-exit — otherwise under-constrained
   drawings burn the retry on an unfixable failure.
3. `Corner` must keep the negative-coordinate clamp; `ObserverOutput.unit` must
   keep the None/blank→"unspecified" coercion.
4. `JointPlacementOutput.joints` must stay **required** (no default): a missing
   key means a malformed call (→ degrade with warning) and must be
   distinguishable from a deliberate empty list.
5. Adding a field: give it a default, update the prompt example, update
   `build_output`, check `determinacy`/`validity` consumers, update
   docs/PROJECT_CONTEXT.md §6.
6. Removing/renaming: grep everything (`pipeline.py`, prompts, exporters,
   frontend `index.tsx`, docs).

---

## Behavioral Guidelines (for AI assistants working in this repo)

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### Think Before Coding
- State assumptions explicitly. If uncertain, ask. If multiple interpretations
  exist, present them. If a simpler approach exists, say so.

### Simplicity First
- Minimum code that solves the problem. No speculative features, abstractions,
  or configurability. If 200 lines can be 50, simplify — **but** do not
  "simplify" away the isolation boundaries described above; they look redundant
  by design.

### Surgical Changes
- Touch only what you must. Don't refactor unrelated code. Match existing style.
  Mention unrelated issues; don't fix them unasked. Remove code made dead by
  your change; leave other dead code (notably `geometry/render.py` — it is a
  kept design reference, documented in docs/REPO_AUDIT.md).

### Goal-Driven Execution
- For non-trivial tasks: state the plan → identify files → implement → verify
  (run the pipeline on test images, twice) → summarize.

### Engineering Rules (restated, non-negotiable)
- Geometry only from explicit dimensions and arithmetic on them. No symmetry,
  centerline, convention, or visual-estimation assumptions. If geometry cannot
  be uniquely determined, report missing constraints — never invent geometry.
- Prefer deterministic Python over LLM reasoning. LLMs: OCR, shape recognition,
  topology. Code: arithmetic, validation, consistency, calculations.
- Frontend interpretability over visual complexity.
