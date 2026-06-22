"""
prompts/joint_prompt.py
------------------------
Agent 2b: Joint Placement.
Runs as a SEPARATE Gemini call, only after geometry (corners/components) is
already fixed by the Inferencer. Receives that geometry as read-only ground
truth. Its output schema (JointPlacementOutput) has no corners/components
field, so it has no path back into geometry - joints are metadata placed ON
geometry, geometry never depends on joints.
"""

import json

JOINT_PROMPT_TEMPLATE = """
You are placing joint markers onto a structural section whose geometry has
ALREADY been computed and fixed. Do NOT recompute, question, or alter the
geometry below - treat it as ground truth.

## FIXED GEOMETRY (already correct - read-only)
Components:
{components_json}

## JOINTS TO PLACE (from the drawing observation)
{joints_json}

## JOINT-LOCATOR DIMENSIONS (numeric offsets that position each joint)
{joint_dims_json}

## YOUR TASK
For each joint in "JOINTS TO PLACE":
1. Find the component(s) in "FIXED GEOMETRY" whose name corresponds to each
   wall label in its "connects" list (wall labels appear as part of the
   component name, e.g. "W1" matches a component named "...member_W1").
2. Using the joint's location_description and the matching joint-locator
   dimension(s), compute "start" and "end" as {{x, y}} points that lie ON the
   boundary of the connected component(s) - i.e. the joint is a point or short
   segment on an edge that already exists, never a new edge.
3. "connects" in your output must be the same wall labels given in the input.

Do NOT invent a joint that was not listed. Do NOT change which walls a joint
connects. If a joint's location cannot be determined from the geometry and
dimensions given, omit it rather than guessing.

## OUTPUT FORMAT
Return ONLY valid JSON. No explanation. No markdown fences.
{{
  "joints": [
    {{"name": "J1", "start": {{"x": 270, "y": 90}}, "end": {{"x": 290, "y": 90}}, "connects": ["W1", "W2"]}}
  ]
}}
If no joint's location can be determined, return {{"joints": []}}.
""".strip()


def build_joint_prompt(observation: dict, inference: dict) -> str:
    return JOINT_PROMPT_TEMPLATE.format(
        components_json=json.dumps(inference.get("components", []), indent=2),
        joints_json=json.dumps(observation.get("joints", []), indent=2),
        joint_dims_json=json.dumps(observation.get("joint_locator_dimensions", []), indent=2),
    )
