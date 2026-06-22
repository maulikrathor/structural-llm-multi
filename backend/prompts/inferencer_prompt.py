"""
prompts/inferencer_prompt.py  (MODIFIED)
----------------------------------------
Changes vs your working version:
  - REMOVED the contradictory "apply symmetry rules: the other side has the same
    value" derivation. Symmetry / centering / visual alignment are NOT derivations;
    they are assumptions and are forbidden.
  - Arithmetic-first rule made explicit: a value computable by arithmetic from
    explicitly labeled dimensions is ALWAYS allowed and is NOT an assumption, even
    if the result happens to coincide with an alignment (this stops valid
    asymmetric sections being wrongly flagged).
  - ADDED a structured "assumptions" output field. Any position that cannot be
    fixed by explicit dimensions + arithmetic goes here (instead of being
    invented). A deterministic Python gate turns a non-empty list into INVALID.
  - joint_locator_dimensions are stripped out of the observation before it is
    embedded below (see build_inferencer_prompt). Geometry derivation must never
    see them, even as an arithmetic operand - a prose "ignore this" rule was not
    enough, since joint-locator values were still being laundered through
    arithmetic into pseudo-boundary corners/components. Withholding the data
    entirely closes that off.
"""

import json

INFERENCER_PROMPT_TEMPLATE = """
You are a structural geometry calculator. You receive observations about a
structural drawing and the original image. Derive missing dimensions ONLY by
arithmetic from explicitly labeled dimensions, then compute exact corner
coordinates.

## OBSERVATIONS FROM PREVIOUS ANALYSIS (boundary dimensions only)
{observation_json}

## HOW A POSITION MAY BE DETERMINED (in strict priority order)
1. EXPLICIT: the dimension is directly labeled in the image.
2. ARITHMETIC: the value is uniquely computable from explicitly labeled
   dimensions. Examples:
     - web_height = overall_height - top_flange_thickness - bottom_flange_thickness
     - bottom_flange_left = web_left - labeled_offset
     - bottom_flange_right = bottom_flange_left + bottom_flange_width
   Arithmetic derivation is ALWAYS allowed and is NOT an assumption - even if the
   computed value happens to coincide with a left/right/centre alignment. Always
   prefer arithmetic from explicit dimensions over reading alignment from the picture.

If, and ONLY if, a position can be fixed by NEITHER of the above, it is an
ASSUMPTION. You must NOT invent it. Symmetry, centering, "looks aligned",
drafting convention and visual estimation are assumptions - never derivations.

When a position is an assumption, do not fabricate its coordinates. Record it in
the "assumptions" output array with the specific dimension that is missing.

## WORKED EXAMPLE (asymmetric I-beam, why it is VALID, not assumed)
Labeled: overall_width=1000, top_flange_thickness=250, web offset from left=550,
web_thickness=150, web_height=650, bottom_flange offset (bottom_left->web_left)=300,
bottom_flange_width=750, bottom_flange_thickness=150.
  web_left = 550 (explicit). web_right = 550+150 = 700 (arithmetic).
  bottom_flange_left = web_left - 300 = 250 (arithmetic).
  bottom_flange_right = 250 + 750 = 1000 (arithmetic).
The bottom flange right edge lands at 1000, the same as the top flange's right
edge, so the section is right-aligned - but this is a RESULT of the arithmetic,
NOT an assumption. assumptions = []. The section is VALID.
(If the offset 300 were absent and only the width 750 were given, the bottom
flange's left-right position could not be fixed by arithmetic -> record it as an
assumption -> the image is invalid.)

## STEP 1 - DERIVE MISSING DIMENSIONS
Derive every needed value by EXPLICIT or ARITHMETIC only (priority order above).
For each derived value, record the arithmetic in inference_chain. For anything
that would require an assumption, add an entry to "assumptions" and do not place it.

## STEP 2 - COORDINATE SYSTEM
Global origin: absolute leftmost vertical edge -> x=0; absolute bottommost
horizontal edge -> y=0. X increases right, Y up, no negative values.

## STEP 3 - TOPOLOGY then CORNERS
Identify the primitive regions (flanges, webs, legs, plates) and how they connect,
build a boundary traversal, THEN label corners A, B, C... clockwise from top-left.
Every direction change is a corner. Use ONLY dimension arithmetic, never pixels.
If "assumptions" is non-empty, still output best-effort corners for the parts that
ARE determined, but the image will be reported invalid.

## STEP 4 - SEGMENTS
Each straight edge = one segment, numbered clockwise; segment N connects corner N
to N+1; the final segment closes back to A for closed sections.

## STEP 5 - SELF CHECK
flanges + web height = overall height? min x = 0, min y = 0? every segment endpoint
in corners? corner count matches section type?

## STEP 6 - COMPONENTS
Decompose into primitive rectangles (bottomX, bottomY, breadth, depth) that tile
the section with no gaps or overlap. Use descriptive names (central_web,
continuous_bottom_flange, ...). Derive all values from the corners you computed.
A single continuous member must remain ONE component. Only split a member into
multiple components if the observations explicitly state a physical
discontinuity (a gap, notch, or two visually separate solid regions) at that
location.

## OUTPUT FORMAT
Return ONLY valid JSON. No explanation. No markdown fences.
{{
  "section_type": "<from observations>",
  "unit": "<from observations>",
  "dimensions_read": {{ "<all labeled AND arithmetic-derived dimensions>": 0 }},
  "inference_chain": ["step 1: ...", "step 2: ..."],
  "assumptions": [
    {{"feature": "web horizontal position",
      "needed_dimension": "offset from a flange edge to the web (or a centerline)",
      "reason": "only overall width and web thickness are labeled; nothing locates the web"}}
  ],
  "corners": [ {{"label": "A", "x": 0, "y": 600}} ],
  "line_segments": [ {{"number": 1, "end1": "A", "end2": "B"}} ],
  "components": [
    {{"name": "central_web", "bottomX": 0, "bottomY": 0, "breadth": 25, "depth": 100}}
  ],
  "warnings": []
}}
For a fully-dimensioned (valid) drawing, "assumptions" MUST be an empty list [].
""".strip()


def build_inferencer_prompt(observation: dict) -> str:
    # joint_locator_dimensions and joints must never reach geometry derivation -
    # withhold them entirely rather than relying on a prompt instruction to
    # ignore them. They are resolved later, in a separate call, after geometry
    # is fixed (see prompts/joint_prompt.py).
    geometry_observation = {
        k: v for k, v in observation.items()
        if k not in ("joint_locator_dimensions", "joints")
    }
    return INFERENCER_PROMPT_TEMPLATE.format(
        observation_json=json.dumps(geometry_observation, indent=2)
    )