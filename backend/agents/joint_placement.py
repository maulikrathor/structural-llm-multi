"""
agents/joint_placement.py
--------------------------
Agent 2b: Joint Placement.

Runs as its own pipeline node, strictly AFTER geometry has passed validation
and the retry loop has concluded - state["inference"] is frozen geometry by
the time this node runs. Read-only over that geometry: its own output schema
(JointPlacementOutput) has no corners/components field, so it has no path
back into geometry. This node has no outgoing retry edge in the pipeline
graph, so a joint problem can never trigger a geometry retry.

On any failure (bad JSON, schema mismatch, no resolvable location) this node
degrades gracefully: joints=[], a warning is recorded, and geometry is left
completely untouched. It must never raise.
"""

from agents.gemini_caller import call_gemini
from prompts.joint_prompt import build_joint_prompt
from schemas import JointPlacementOutput


async def run_joint_placement(state: dict) -> dict:
    """
    LangGraph node for Agent 2b.
    Reads state["observation"], state["inference"] (frozen geometry),
    state["image_bytes"], state["mime_type"].
    Writes inference["joints"]. Never mutates corners/components/segments.
    """
    observation: dict = state.get("observation") or {}
    inference: dict = dict(state.get("inference") or {})
    image_bytes: bytes = state["image_bytes"]
    mime_type: str = state["mime_type"]

    joints_observed = observation.get("joints") or []
    if not joints_observed:
        inference["joints"] = []
        return {**state, "inference": inference}

    print(f"[stage:joint_placement:call] calling Gemini ({len(joints_observed)} joint(s))")
    try:
        raw = await call_gemini(
            system_prompt=build_joint_prompt(observation, inference),
            user_text="Place each joint onto the fixed geometry above. Return only valid JSON.",
            image_bytes=image_bytes,
            mime_type=mime_type,
            agent_name="joint_placement",
        )
        validated = JointPlacementOutput(**raw)
        print(f"[stage:joint_placement:validate] schema OK, joints={len(validated.joints)}")
        inference["joints"] = [j.model_dump() for j in validated.joints]
    except Exception as e:
        print(f"[stage:joint_placement] FAILED, degrading gracefully: {e}")
        inference.setdefault("warnings", []).append(f"Joint placement failed: {e}")
        inference["joints"] = []

    return {**state, "inference": inference}
