"""
agents/inferencer.py
--------------------
Agent 2: Derives missing dimensions and computes all corner coordinates.
Receives Agent 1 observation. Has access to original image.
"""

from pydantic import ValidationError
from agents.gemini_caller import call_gemini
from prompts.inferencer_prompt import build_inferencer_prompt
from schemas import InferencerOutput


async def run_inferencer(state: dict) -> dict:
    """
    LangGraph node for Agent 2.
    Reads state["observation"], state["image_bytes"], state["mime_type"].
    Writes state["inference"].
    If retry, reads state["validation_errors"] and injects them into prompt.
    """
    observation: dict = state["observation"]
    image_bytes: bytes = state["image_bytes"]
    mime_type: str = state["mime_type"]
    retry_count: int = state.get("retry_count", 0)
    validation_errors: list = state.get("validation_errors", [])

    system_prompt = build_inferencer_prompt(observation)

    user_text = (
        "Using the observations above and this image, derive all missing dimensions "
        "and compute all corner coordinates. Return only valid JSON."
    )

    # On retry: inject previous errors so model self-corrects
    if retry_count > 0 and validation_errors:
        error_str = "\n".join(f"- {e}" for e in validation_errors)
        user_text += (
            f"\n\nPREVIOUS ATTEMPT FAILED VALIDATION. Fix these errors:\n{error_str}"
        )

    raw = await call_gemini(
        system_prompt=system_prompt,
        user_text=user_text,
        image_bytes=image_bytes,
        mime_type=mime_type,
        agent_name="inferencer",
    )

    # Validate against schema
    try:
        validated = InferencerOutput(**raw)
        return {
            **state,
            "inference": validated.model_dump(),
            "validation_errors": [],
        }
    except Exception as e:
        return {
            **state,
            "inference": raw,
            "validation_errors": [str(e)],
        }
