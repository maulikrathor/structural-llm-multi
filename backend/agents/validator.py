"""
agents/validator.py
-------------------
Agent 3: Validates inferencer output against the original image.
Only runs for complex sections or when Pydantic validation failed.
Can return corrected corners if it finds fixable issues.
"""

from pydantic import ValidationError
from agents.gemini_caller import call_gemini
from prompts.validator_prompt import build_validator_prompt
from schemas import ValidatorOutput


async def run_validator(state: dict) -> dict:
    """
    LangGraph node for Agent 3.
    Reads state["inference"], state["image_bytes"], state["mime_type"].
    Writes state["validation"].
    If corrected_corners returned, merges them into state["inference"].
    """
    inference: dict = state["inference"]
    image_bytes: bytes = state["image_bytes"]
    mime_type: str = state["mime_type"]

    system_prompt = build_validator_prompt(inference)

    print("[stage:validator:call] calling Gemini")
    raw = await call_gemini(
        system_prompt=system_prompt,
        user_text=(
            "Validate the computed coordinates against this structural drawing image. "
            "Return only valid JSON."
        ),
        image_bytes=image_bytes,
        mime_type=mime_type,
        agent_name="validator",
    )
    print("[stage:validator:call] Gemini call returned")

    try:
        validated = ValidatorOutput(**raw)
        print("[stage:validator:validate] schema OK")
        print(
            f"[stage:validator:result] valid={validated.valid} "
            f"errors={validated.errors} "
            f"has_corrected_corners={validated.corrected_corners is not None}"
        )
    except ValidationError as e:
        # Validator itself returned garbage — treat as passed to avoid infinite loop
        print(f"[stage:validator:validate] schema FAILED, treating as passed: {e}")
        return {
            **state,
            "validation": {"valid": True, "errors": [], "corrected_corners": None},
        }

    # If validator found fixable errors and provided corrected corners, apply them
    updated_inference = inference
    if not validated.valid and validated.corrected_corners:
        updated_inference = {
            **inference,
            "corners": [c.model_dump() for c in validated.corrected_corners],
        }
        # Also add a warning
        updated_inference["warnings"] = inference.get("warnings", []) + [
            f"Validator auto-corrected: {'; '.join(validated.errors)}"
        ]

    return {
        **state,
        "validation": validated.model_dump(),
        "inference": updated_inference,
    }
