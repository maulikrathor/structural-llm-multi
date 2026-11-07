"""
prompts/joint_prompt.py
------------------------
Agent 2b: Joint Placement.
Runs as a SEPARATE Gemini call, only after geometry (corners/components/
line_segments) is already fixed by the Inferencer. Receives that geometry as
read-only ground truth. Its output schema (JointPlacementOutput) has no
corners/components field, so it has no path back into geometry - joints are
an annotation layer on top of geometry, geometry never depends on joints.

Joint Placement is the SOLE owner of joint extraction. Observer has no
involvement - it does not catalog markers, does not classify dimensions by
purpose, and supplies no semantic hints (no "connects", no location
descriptions). Every red marker must be detected directly from the image;
the supplied geometry establishes only the coordinate reference frame
(origin, axes, scale), never a substitute for visually finding the marker.
"""

import json

JOINT_PROMPT_TEMPLATE = """
You are detecting red joint marker lines directly from a structural section
image. The section's geometry has ALREADY been computed and fixed. Do NOT
recompute, question, or alter the geometry below - use it only to establish
the coordinate reference frame (origin, axes, scale) for this image.

## FIXED GEOMETRY (already correct - read-only; coordinate reference frame only)
Corners:
{corners_json}
Components:
{components_json}
Line segments:
{line_segments_json}

## YOUR TASK
1. Visually scan the entire image for every short RED marker line drawn on
   top of the structural outline (same tick/end-cap style as the black
   dimension lines). There are no printed joint labels - you are detecting
   these directly from pixels, not reading them from text.
2. Assign each one a name sequentially as you find it, scanning
   left-to-right then top-to-bottom: "J1", "J2", "J3", and so on.
3. For each marker, determine its orientation (horizontal or vertical) and
   its two endpoints by reading the marker's actual drawn position in the
   image. Do NOT derive or estimate a marker's position from a component's
   name, from which component it appears to be "near", or from any textual
   description - there is none provided, and none should be assumed. You
   must visually identify the marker itself.
4. Report each endpoint as an {{x, y}} point in the same coordinate system
   as the geometry above (origin at the structure's own leftmost/bottommost
   edge, X increasing right, Y increasing up).

Do NOT treat a marker as defining a new component, corner, or segment - the
geometry above is fixed and joints never alter it. Do NOT invent a marker
that is not actually visible in the image. If a marker is visible but its
endpoints cannot be confidently determined, omit it rather than guessing.

## OUTPUT FORMAT
Return ONLY valid JSON. No explanation. No markdown fences.
{{
  "joints": [
    {{"name": "J1", "start": {{"x": 270, "y": 90}}, "end": {{"x": 290, "y": 90}}}}
  ]
}}
If no red markers are found, return {{"joints": []}}.
""".strip()


def build_joint_prompt(inference: dict) -> str:
    return JOINT_PROMPT_TEMPLATE.format(
        corners_json=json.dumps(inference.get("corners", []), indent=2),
        components_json=json.dumps(inference.get("components", []), indent=2),
        line_segments_json=json.dumps(inference.get("line_segments", []), indent=2),
    )
