"""
schemas.py
----------
Pydantic models for each agent's input/output.
These define what valid output looks like at each stage.
"""

from pydantic import BaseModel, field_validator, model_validator
from typing import Optional


# ── Agent 1: Observer Output ──────────────────────────────────────────────────

class LabeledDimension(BaseModel):
    name: str               # e.g. "top_flange_thickness"
    value: float
    location: str           # e.g. "top left, vertical arrow"

class JointObservation(BaseModel):
    name: str                  # e.g. "J1"
    connects: list[str]        # raw wall labels visible near the joint, e.g. ["W1", "W2"]
    location_description: str  # e.g. "circle mark on W1, near the 30-offset arrow"

class ObserverOutput(BaseModel):
    section_type: str
    unit: str = "unspecified"   # "unspecified" when no unit text is visible in the drawing
    is_symmetric: bool
    has_unlabeled_dims: bool
    # boundary_dimensions define/derive the structural outline and are the ONLY
    # dimensions the Inferencer may use for geometry (corners/segments/components).
    boundary_dimensions: list[LabeledDimension]
    # joint_locator_dimensions merely position a joint marker along an already-
    # existing member; they must never reach geometry derivation.
    joint_locator_dimensions: list[LabeledDimension] = []
    # raw joint catalog (labels + connected walls) — pre-coordinate. Joint
    # placement (start/end) is resolved later, after geometry is fixed.
    joints: list[JointObservation] = []
    topology_notes: str     # free text: "open bottom", "two webs", etc.
    alignment_notes: Optional[str] = None  # e.g. "shorter bottom flange is center-aligned"
    complexity: str         # "simple" or "complex"
    # complexity drives whether Validator runs:
    # simple = standard symmetric section, all dims labeled
    # complex = asymmetric, unlabeled dims, or unusual shape

    @field_validator('unit', mode='before')
    @classmethod
    def unit_none_or_blank_is_unspecified(cls, v):
        # Gemini sends null/"" when no unit text exists in the drawing — never
        # invent a unit (mm/cm/in), record the absence explicitly instead.
        if v is None or (isinstance(v, str) and not v.strip()):
            return "unspecified"
        return v

    @field_validator('section_type')
    @classmethod
    def section_type_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("section_type cannot be empty")
        return v

    @field_validator('complexity')
    @classmethod
    def complexity_valid(cls, v):
        if v not in ("simple", "complex"):
            raise ValueError("complexity must be 'simple' or 'complex'")
        return v


# ── Agent 2: Inferencer Output ────────────────────────────────────────────────

class Assumption(BaseModel):
    feature: str
    needed_dimension: str
    reason: str = ""

class Corner(BaseModel):
    label: str
    x: float
    y: float

    @field_validator('x', 'y')
    @classmethod
    def no_negative_coords(cls, v):
        if v < -0.001:  # small tolerance for float precision
            raise ValueError(f"Coordinate cannot be negative, got {v}")
        return max(v, 0.0)

class Segment(BaseModel):
    number: int
    end1: str
    end2: str

class StructuralComponent(BaseModel):
    name: str           # e.g. "left_vertical_leg", "top_flange", "bottom_plate"
    bottomX: float
    bottomY: float
    breadth: float      # width (x-direction)
    depth: float        # height (y-direction)

class InferencerOutput(BaseModel):
    section_type: str
    unit: str
    dimensions_read: dict
    inference_chain: list[str]   # step-by-step reasoning, e.g. ["web_left_x = 150/2 - 6/2 = 72"]
    assumptions: list[Assumption] = []  # positions that could NOT be fixed by arithmetic
    corners: list[Corner]
    line_segments: list[Segment]
    components: list[StructuralComponent]
    warnings: list[str]

    @model_validator(mode='after')
    def geometry_constraints(self):
        # When assumptions are present the drawing is underdetermined; geometry
        # validity is handled by assess_validity() in build_output, not here.
        # Skipping here prevents a spurious retry for an unfixable structural issue.
        if self.assumptions:
            return self
        if len(self.corners) < 4:
            raise ValueError(f"Too few corners: {len(self.corners)}. Minimum is 4.")
        if len(self.components) < 1:
            raise ValueError("components list cannot be empty")
        xs = [c.x for c in self.corners]
        ys = [c.y for c in self.corners]
        if min(xs) > 0.1:
            raise ValueError(f"No corner at x=0. Min x is {min(xs)}. Origin rule violated.")
        if min(ys) > 0.1:
            raise ValueError(f"No corner at y=0. Min y is {min(ys)}. Origin rule violated.")
        labels = {c.label for c in self.corners}
        for seg in self.line_segments:
            if seg.end1 not in labels:
                raise ValueError(f"Segment {seg.number} end1='{seg.end1}' not in corners")
            if seg.end2 not in labels:
                raise ValueError(f"Segment {seg.number} end2='{seg.end2}' not in corners")
        return self


# ── Agent 2b: Joint Placement (separate call, runs only after geometry is
#     fixed; this schema has no corners/components field so it has no path
#     back into geometry) ───────────────────────────────────────────────────

class Point(BaseModel):
    x: float
    y: float

class Joint(BaseModel):
    name: str               # e.g. "J1"
    start: Point
    end: Point
    connects: list[str]     # wall labels, e.g. ["W1", "W2"]

class JointPlacementOutput(BaseModel):
    # No default: a response missing "joints" entirely is a malformed/failed
    # call and should raise (caught by _resolve_joints, which degrades to []
    # with a warning) rather than silently looking identical to a deliberate
    # "no joint could be determined" {"joints": []}.
    joints: list[Joint]


# ── Agent 3: Validator Output ─────────────────────────────────────────────────

class ValidatorOutput(BaseModel):
    valid: bool
    errors: list[str]        # empty if valid=True
    corrected_corners: Optional[list[Corner]] = None   # if validator can fix minor issues