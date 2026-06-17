"""
agents/observer.py
------------------
Agent 1: Observes the image. Reports what is explicitly visible.
No inference. No calculation. Just observation.
"""

from pydantic import ValidationError
from agents.gemini_caller import call_gemini
from prompts.observer_prompt import OBSERVER_PROMPT
from schemas import ObserverOutput


async def run_observer(state: dict) -> dict:
    """
    LangGraph node for Agent 1.
    Reads state["image_bytes"] and state["mime_type"].
    Writes state["observation"] and updates state["errors"].
    """
    image_bytes: bytes = state["image_bytes"]
    mime_type: str = state["mime_type"]

    raw = await call_gemini(
        system_prompt=OBSERVER_PROMPT,
        user_text="Observe this structural drawing. Report only what is explicitly visible. Return only valid JSON.",
        image_bytes=image_bytes,
        mime_type=mime_type,
        agent_name="observer",
    )

    try:
        validated = ObserverOutput(**raw)
        return {
            **state,
            "observation": validated.model_dump(),
            "errors": [],
        }
    except ValidationError as e:
        # Hard stop: passing unvalidated observation data downstream corrupts
        # all subsequent agents. Surface the schema error immediately.
        raise ValueError(
            f"Observer returned output that failed schema validation — "
            f"cannot continue pipeline. "
            f"Fix: check the observer prompt JSON example matches ObserverOutput fields. "
            f"Details: {str(e)}"
        ) from e
