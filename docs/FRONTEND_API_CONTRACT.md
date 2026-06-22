# Frontend API Contract — Structural Section Analyzer

Source of truth: `backend/main.py`, `backend/pipeline.py`, `backend/schemas.py`,
`backend/geometry/validity.py`, `backend/exporters.py`. Generated from the
current backend implementation — update this file if any of those change.

---

## 1. Endpoints

### `GET /api/health`

Liveness check. No auth, no params.

**Response 200**
```json
{ "status": "ok" }
```

### `POST /api/analyze`

The only functional endpoint. Runs the 3-agent pipeline (Observer → Inferencer
→ Validator) on a single uploaded image and returns geometry + export files.

---

## 2. Request Schema

| Property | Value |
|---|---|
| Method | `POST` |
| Content-Type | `multipart/form-data` |
| Body field | `file` (binary, required) |
| Allowed MIME types | `image/png`, `image/jpeg`, `image/jpg`, `image/webp` |
| Max file size | 10 MB |

```ts
const formData = new FormData();
formData.append("file", file); // File from <input type="file"> or drop event

await fetch(`${apiUrl}/api/analyze`, { method: "POST", body: formData });
```

No other fields, query params, or headers are read by the backend (CORS is
controlled server-side via `CORS_ORIGINS` env var, not by the client).

---

## 3. Response Schema (200 OK)

```ts
interface AnalyzeResponse {
  analysis: Analysis;
  exports: Exports;
}

interface Analysis {
  section_type: string;
  unit: string;
  dimensions_read: Record<string, number>;
  corners: Corner[];
  line_segments: Segment[];
  components: Component[];
  warnings: string[];
}

interface Corner {
  label: string;   // "A", "B", ... "Z", "AA", "AB", ...
  x: number;
  y: number;
}

interface Segment {
  number: number;
  end1: string;    // references a Corner.label
  end2: string;    // references a Corner.label
}

interface Component {
  name: string;     // e.g. "left_vertical_leg", "top_flange"
  bottomX: number;
  bottomY: number;
  breadth: number;  // width, x-direction
  depth: number;    // height, y-direction
}

interface Exports {
  excel_b64: string; // base64-encoded .xlsx (Point Table + Line Segment Table sheets)
  dxf_b64: string;   // base64-encoded .dxf
}
```

### Field-by-field notes

| Field | Always present? | Notes |
|---|---|---|
| `analysis.section_type` | Yes | Falls back to `"unknown"` if inference and observation both lack it. |
| `analysis.unit` | Yes | Literal string `"unspecified"` when no unit text is visible anywhere in the source image — **never** a guessed unit (mm/cm/in). Frontend should display this distinctly (e.g. "unit: unspecified", not blank). |
| `analysis.dimensions_read` | Yes | May be `{}`. Free-form key → numeric value map (all explicit + arithmetic-derived dimensions). No fixed key set — do not hard-code expected keys. |
| `analysis.corners` | Yes (array, may be `[]`) | Empty when the validity gate rejects the geometry (see §5). When non-empty, guaranteed: every coordinate ≥ 0, and at least one corner has `x=0` and one has `y=0` (origin rule). |
| `analysis.line_segments` | Yes (array, may be `[]`) | `end1`/`end2` are guaranteed to reference labels present in `corners` whenever `corners` is non-empty. Empty together with `corners`. |
| `analysis.components` | Yes (array, may be `[]`) | Rectangular decomposition of the section. Empty together with `corners`. **Not currently rendered by the frontend** — `AnnotatedCanvas`/`ResultTables` only consume `corners`/`line_segments` today; this is available for a future frontend addition. |
| `analysis.warnings` | Yes (array, may be `[]`) | See §6 for the taxonomy of messages that can appear here. |

### `assumptions` is NOT part of the response

Internally, the Inferencer's LLM call produces a structured `assumptions: Assumption[]`
field (`{feature, needed_dimension, reason}`) for any position it could not
fix by explicit dimensions + arithmetic. This field:
- exists only in the backend's internal `InferencerOutput` Pydantic model,
- is **consumed by the validity gate** (`geometry/validity.py::assess_validity`),
- is **converted into a single human-readable sentence appended to `warnings`**
  and the geometry arrays are blanked (see §5),
- is **never serialized into the API response**.

Frontend code should not look for an `assumptions` key anywhere in the response.

---

## 4. Error Responses

Every error path returns a JSON body of the shape `{ "detail": string }`. There
is no machine-readable error code field — match on HTTP status, display `detail` as-is.

| Status | Cause | Example `detail` |
|---|---|---|
| 400 | Unsupported MIME type | `"Unsupported file type: text/plain. Use PNG, JPEG, or WebP."` |
| 400 | File exceeds 10 MB | `"File too large. Max 10MB."` |
| 422 | Pipeline raised `ValueError` (e.g. no `final_result` produced) | `"Pipeline completed but produced no output"` |
| 500 | Any other unexpected exception (Gemini call failure, network error, etc.) | `"Analysis failed: RuntimeError: Gemini inferencer failed with HTTP 503: ..."` |

```ts
const res = await fetch(url, { method: "POST", body: formData });
const text = await res.text();
if (!res.ok) {
  let detail = text;
  try { detail = JSON.parse(text).detail; } catch {}
  throw new Error(detail || "Analysis failed");
}
```

---

## 5. Validation / Geometry States

The backend resolves to exactly one of two geometry states per request — there
is no partial/degraded geometry state exposed to the frontend:

### State A — Determined (usable geometry)
- `corners`, `line_segments`, `components` are all non-empty.
- `warnings` may still contain **non-fatal** entries:
  - Component-tiling inconsistencies (gaps/overlaps detected by shapely union check)
  - Origin tolerance notes
  - `"Determinacy warning: ..."` — an independent, secondary axis-spanning
    check (`geometry/determinacy.py`). This check is currently **advisory only**:
    it can fire even when geometry is returned, and does **not** blank the
    geometry. Treat it as a lower-confidence warning, not a rejection.
- Frontend should render the diagram and tables normally; surface `warnings`
  as non-blocking notices (e.g. amber banners), not errors.

### State B — Underdetermined (rejected geometry)
- `corners = []`, `line_segments = []`, `components = []`.
- `warnings` contains exactly one explanatory sentence of the form:
  > `"This drawing is under-constrained - the following cannot be determined
  > from the labeled dimensions by arithmetic alone, and no assumption
  > (symmetry, centering, alignment) is permitted: <feature> (needs: <dimension>); ...`
- This is a **deterministic, code-level rejection** (not an LLM opinion) —
  triggered whenever the Inferencer reports it could not place a feature using
  only explicit dimensions + arithmetic.
- Frontend should treat this as "analysis could not produce geometry" —
  display the warning text prominently (it names the missing dimension so the
  user knows what to add to the drawing) and suppress/disable the diagram,
  tables, and export buttons rather than rendering empty ones.

### Known limitation — no explicit "best-effort" flag
If both Pydantic retries are exhausted (`agents/inferencer.py` failed schema
validation twice), the pipeline still proceeds to build output from whatever
the last attempt produced, then runs it through the same validity gate above.
There is **no separate flag** distinguishing "clean first-try success" from
"succeeded only after exhausting retries" — both look like State A to the
frontend. If you need to surface retry exhaustion, it would need a new field
(not currently emitted).

A `"Pipeline: ..."` or `"Validation warning: ..."` prefix in `warnings`
indicates, respectively, a pipeline-level error that didn't block output, or
that Agent 3 (Validator) flagged something while the pipeline still chose to
output (no auto-correction was available). Both can co-occur with State A.

---

## 6. Warnings Taxonomy

`warnings: string[]` is a flat array; entries are plain sentences meant for
direct display. Recognize these prefixes/shapes if you want to style them differently:

| Pattern | Source | Meaning |
|---|---|---|
| `"Pipeline: <msg>"` | `pipeline.py` `state["errors"]` | A non-fatal pipeline-level issue (e.g. Observer schema mismatch) occurred but processing continued. |
| `"Validation warning: <msg>"` | Agent 3 (Validator) | Validator flagged an issue with no auto-fix available, but the pipeline output anyway (retries exhausted or no correction provided). |
| `"This drawing is under-constrained - ...permitted: ... ."` | `geometry/validity.py` (assumptions gate) | State B trigger — see §5. Geometry is blanked. |
| `"origin: smallest x is ..."` / `"...smallest y is ..."` | `geometry/validity.py` consistency check | Geometry returned but origin isn't exactly at 0 (tolerance 0.5). |
| `"negative coordinates present"` | same | Should not normally occur (schema clamps negatives), advisory only. |
| `"components leave ... uncovered"` / `"...overlap or exceed..."` | same (shapely tiling check) | Components don't perfectly tile the outline polygon — geometry still returned. |
| `"Determinacy warning: <reason>"` | `geometry/determinacy.py` (secondary, advisory) | Independent axis-spanning check disagrees with the Inferencer's self-report. Advisory only; geometry not blanked. |

No warning carries a severity field — severity is implied entirely by which
prefix (or lack of one) it has, per the table above.

---

## 7. Loading States

There is a single synchronous request/response cycle — **no streaming,
polling, SSE, or WebSocket**. The frontend must model this as one long-running
request:

- Typical latency: a few seconds to ~1–2 minutes. The pipeline makes 2–4
  sequential Gemini calls (Observer, Inferencer, optional Validator, optional
  one retry of Inferencer), each with up to a 120s HTTP timeout and up to 3
  internal retries on HTTP 429/503 (with backoff up to ~60s per retry).
- Worst case (multiple 503/429 retries across multiple agent calls) can take
  several minutes. Use an indeterminate spinner, not a progress bar — the
  backend exposes no intermediate progress signal.
- Recommend a client-side fetch timeout well above 2 minutes (e.g. 5 minutes)
  to avoid aborting a request the backend would have eventually completed.

---

## 8. Quick Reference — curl

```bash
curl -X POST http://localhost:8000/api/analyze \
  -F "file=@drawing.png;type=image/png"
```

```bash
curl http://localhost:8000/api/health
```
