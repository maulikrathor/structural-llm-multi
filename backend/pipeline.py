"""
pipeline.py
-----------
LangGraph graph wiring all agents.

Flow:
  observe → infer → [pydantic_check] →
    if simple + valid   → place_joints → output
    if complex          → validate → place_joints → output
    if invalid + retry  → infer (retry with errors injected)
    if invalid + max_retry → place_joints → output with warnings (best effort)

place_joints runs strictly AFTER the geometry retry loop has concluded
(geometry is frozen by this point) and has NO outgoing edge back into infer
or validate - a joint problem can never trigger a geometry retry. The
validator never receives joint data, so its "errors" (which DO feed the
retry loop) can never be about joints either. See agents/joint_placement.py.

Max retries: 1 (so max 4 geometry-side Gemini calls: observe + infer +
validate + retry_infer, plus one optional place_joints call.)
"""

from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END

from agents.observer import run_observer
from agents.inferencer import run_inferencer
from agents.validator import run_validator
from agents.joint_placement import run_joint_placement
from geometry.validity import assess_validity
from geometry.determinacy import check_determinacy

MAX_RETRIES = 1


# ── State Definition ──────────────────────────────────────────────────────────

class PipelineState(TypedDict):
    # Inputs
    image_bytes: bytes
    mime_type: str

    # Agent outputs
    observation: Optional[dict]
    inference: Optional[dict]
    validation: Optional[dict]

    # Control
    retry_count: int
    validation_errors: list
    errors: list

    # Final
    final_result: Optional[dict]


# ── Routing Functions ─────────────────────────────────────────────────────────

def route_after_infer(state: PipelineState) -> str:
    """
    After inferencer runs, decide next step:
    - If Pydantic validation failed AND retries left → retry (back to inferencer)
    - If Pydantic validation failed AND no retries left → finalize anyway (best effort)
    - If valid AND complex section → run validator
    - If valid AND simple section → finalize directly (save API call)
    "output" here means "geometry phase is done" - the graph routes that to
    place_joints, never directly to the output node (see build_pipeline).
    """
    validation_errors = state.get("validation_errors", [])
    retry_count = state.get("retry_count", 0)
    observation = state.get("observation", {})
    complexity = observation.get("complexity", "simple")

    if validation_errors:
        if retry_count < MAX_RETRIES:
            return "retry"
        else:
            # Max retries hit — pass through with warning
            return "output"

    if retry_count >= MAX_RETRIES:
        return "output"

    if complexity == "complex":
        return "validate"

    return "output"


def route_after_validate(state: PipelineState) -> str:
    """
    After validator runs:
    - If valid or corrected → finalize (routes to place_joints, see build_pipeline)
    - If invalid and retries left → retry inferencer
    - If invalid and no retries → finalize best effort
    """
    validation = state.get("validation", {})
    retry_count = state.get("retry_count", 0)

    print(
        f"[stage:route_after_validate] valid={validation.get('valid')} "
        f"errors={validation.get('errors')} "
        f"corrected_corners_present={validation.get('corrected_corners') is not None} "
        f"retry_count={retry_count} max_retries={MAX_RETRIES}"
    )

    if validation.get("valid", True):
        print("[stage:route_after_validate] decision=output (valid=True)")
        return "output"

    has_corrections = validation.get("corrected_corners") is not None
    if has_corrections:
        print("[stage:route_after_validate] decision=output (corrections already applied)")
        return "output"  # validator already applied corrections in its node

    if retry_count < MAX_RETRIES:
        print("[stage:route_after_validate] decision=retry (invalid, no corrections, retries remain)")
        return "retry"

    print("[stage:route_after_validate] decision=output (invalid, no corrections, retries exhausted)")
    return "output"


# ── Retry Node ────────────────────────────────────────────────────────────────

def increment_retry(state: PipelineState) -> PipelineState:
    """Increments retry count. LangGraph loops back to inferencer after this."""
    validation = state.get("validation", {})
    validator_errors = validation.get("errors", []) if validation else []
    all_errors = state.get("validation_errors", []) + validator_errors

    return {
        **state,
        "retry_count": state.get("retry_count", 0) + 1,
        "validation_errors": all_errors,
        "validation": None,
    }


# ── Output Node ───────────────────────────────────────────────────────────────

def build_output(state: PipelineState) -> PipelineState:
    """
    Assembles final_result in the exact shape the frontend expects:
    {section_type, unit, dimensions_read, corners, line_segments, components, joints, warnings}
    Strips inference_chain and assumptions (internal reasoning, not needed by frontend).
    Runs the deterministic validity gate to reject under-constrained geometry.
    By this point place_joints has already run, so inference["joints"] is final.
    """
    inference = state.get("inference", {})
    observation = state.get("observation", {})
    validation = state.get("validation", {})

    warnings = list(inference.get("warnings", []) or [])

    for e in (state.get("errors", []) or []):
        warnings.append(f"Pipeline: {e}")

    if validation and not validation.get("valid", True):
        for e in (validation.get("errors", []) or []):
            warnings.append(f"Validation warning: {e}")

    # Deterministic validity gate: rejects geometry derived from assumptions
    # (symmetry/centering/visual alignment) rather than explicit dimensions.
    validity = assess_validity(inference)
    print(f"[stage:assess_validity] valid={validity['valid']} reason={validity.get('reason')}")
    if not validity["valid"]:
        corners, segments, components = [], [], []
        inference = {**inference, "joints": []}  # joints reference components that no longer exist
        if validity.get("reason"):
            warnings.append(validity["reason"])
    else:
        corners = validity["corners"]
        segments = validity["line_segments"]
        components = validity["components"]
        # validity["warnings"] = inference warnings + consistency-check results;
        # add only the new consistency-check entries to avoid duplication.
        for w in validity["warnings"]:
            if w not in warnings:
                warnings.append(w)

        # Secondary determinacy gate: independently verifies that every
        # coordinate in the components can be reached from the origin by
        # consuming exactly one labeled dimension per gap — no symmetry or
        # centering assumptions allowed. Warning-only for now; geometry is
        # not blanked so we can compare outputs during calibration.
        dims = observation.get("dimensions") or []
        det = check_determinacy(components, dims)
        print(f"[stage:determinacy] determined={det['determined']} reason={det.get('reason')}")
        if not det["determined"]:
            warnings.append(f"Determinacy warning: {det['reason']}")

    final_result = {
        "section_type": inference.get("section_type", observation.get("section_type", "unknown")),
        "unit": inference.get("unit", observation.get("unit", "")),
        "dimensions_read": inference.get("dimensions_read", {}),
        "corners": corners,
        "line_segments": segments,
        "components": components,
        "joints": inference.get("joints", []),
        "warnings": warnings,
    }
    print(f"[stage:output] corners={len(corners)} segments={len(segments)} "
          f"components={len(components)} warnings={len(warnings)}")

    return {**state, "final_result": final_result}


# ── Build Graph ───────────────────────────────────────────────────────────────

def build_pipeline():
    graph = StateGraph(PipelineState)

    # Add nodes
    graph.add_node("observe", run_observer)
    graph.add_node("infer", run_inferencer)
    graph.add_node("validate", run_validator)
    graph.add_node("retry", increment_retry)
    graph.add_node("place_joints", run_joint_placement)
    graph.add_node("output", build_output)

    # Entry point
    graph.set_entry_point("observe")

    # Edges
    graph.add_edge("observe", "infer")

    # "output" here routes to place_joints, NOT the output node directly -
    # geometry must be frozen (retry loop concluded) before joints are placed.
    graph.add_conditional_edges(
        "infer",
        route_after_infer,
        {
            "retry": "retry",
            "validate": "validate",
            "output": "place_joints",
        }
    )

    graph.add_edge("retry", "infer")  # loop back with errors injected - geometry only

    graph.add_conditional_edges(
        "validate",
        route_after_validate,
        {
            "retry": "retry",
            "output": "place_joints",
        }
    )

    # place_joints has no outgoing edge back into infer/validate/retry - a
    # joint problem can never trigger a geometry retry. It unconditionally
    # proceeds to output, degrading gracefully internally on failure.
    graph.add_edge("place_joints", "output")

    graph.add_edge("output", END)

    return graph.compile()


# Singleton — compiled once at import time
pipeline = build_pipeline()


# ── Public Entry Point ────────────────────────────────────────────────────────

async def run_pipeline(image_bytes: bytes, mime_type: str) -> dict:
    """
    Run the full multi-agent pipeline.
    Returns final_result dict in the frontend contract shape.
    """
    initial_state: PipelineState = {
        "image_bytes": image_bytes,
        "mime_type": mime_type,
        "observation": None,
        "inference": None,
        "validation": None,
        "retry_count": 0,
        "validation_errors": [],
        "errors": [],
        "final_result": None,
    }

    result = await pipeline.ainvoke(initial_state)

    if result["final_result"] is None:
        raise ValueError("Pipeline completed but produced no output")

    return result["final_result"]