"""
pipeline.py
-----------
LangGraph graph wiring all three agents.

Flow:
  observe → infer → [pydantic_check] → 
    if simple + valid   → output
    if complex          → validate → output  
    if invalid + retry  → infer (retry with errors injected)
    if invalid + max_retry → output with warnings (best effort)

Max retries: 1 (so max 4 Gemini calls: observe + infer + validate + retry_infer)
"""

from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END

from agents.observer import run_observer
from agents.inferencer import run_inferencer
from agents.validator import run_validator

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
    - If Pydantic validation failed AND no retries left → output anyway (best effort)
    - If valid AND complex section → run validator
    - If valid AND simple section → output directly (save API call)
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
    - If valid or corrected → output
    - If invalid and retries left → retry inferencer
    - If invalid and no retries → output best effort
    """
    validation = state.get("validation", {})
    retry_count = state.get("retry_count", 0)

    if validation.get("valid", True):
        return "output"

    has_corrections = validation.get("corrected_corners") is not None
    if has_corrections:
        return "output"  # validator already applied corrections in its node

    if retry_count < MAX_RETRIES:
        return "retry"

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
    {section_type, unit, dimensions_read, corners, line_segments, warnings}
    Strips inference_chain (internal reasoning, not needed by frontend).
    """
    inference = state.get("inference", {})
    observation = state.get("observation", {})
    validation = state.get("validation", {})

    warnings = inference.get("warnings", [])

    # Append any pipeline-level errors as warnings
    pipeline_errors = state.get("errors", [])
    if pipeline_errors:
        warnings = warnings + [f"Pipeline: {e}" for e in pipeline_errors]

    # If validator found errors but we're outputting anyway
    if validation and not validation.get("valid", True):
        validator_errors = validation.get("errors", [])
        warnings = warnings + [f"Validation warning: {e}" for e in validator_errors]

    final_result = {
        "section_type": inference.get("section_type", observation.get("section_type", "unknown")),
        "unit": inference.get("unit", observation.get("unit", "")),
        "dimensions_read": inference.get("dimensions_read", {}),
        "corners": inference.get("corners", []),
        "line_segments": inference.get("line_segments", []),
        "components": inference.get("components", []),
        "warnings": warnings,
    }

    return {**state, "final_result": final_result}


# ── Build Graph ───────────────────────────────────────────────────────────────

def build_pipeline():
    graph = StateGraph(PipelineState)

    # Add nodes
    graph.add_node("observe", run_observer)
    graph.add_node("infer", run_inferencer)
    graph.add_node("validate", run_validator)
    graph.add_node("retry", increment_retry)
    graph.add_node("output", build_output)

    # Entry point
    graph.set_entry_point("observe")

    # Edges
    graph.add_edge("observe", "infer")

    graph.add_conditional_edges(
        "infer",
        route_after_infer,
        {
            "retry": "retry",
            "validate": "validate",
            "output": "output",
        }
    )

    graph.add_edge("retry", "infer")  # loop back with errors injected

    graph.add_conditional_edges(
        "validate",
        route_after_validate,
        {
            "retry": "retry",
            "output": "output",
        }
    )

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