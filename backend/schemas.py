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

class ObserverOutput(BaseModel):
    section_type: str
    unit: str
    is_symmetric: bool
    has_unlabeled_dims: bool
    labeled_dimensions: list[LabeledDimension]
    topology_notes: str     # free text: "open bottom", "two webs", etc.
    alignment_notes: Optional[str] = None  # e.g. "shorter bottom flange is center-aligned"
    complexity: str         # "simple" or "complex"
    # complexity drives whether Validator runs:
    # simple = standard symmetric section, all dims labeled
    # complex = asymmetric, unlabeled dims, or unusual shape

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
    corners: list[Corner]
    line_segments: list[Segment]
    components: list[StructuralComponent]
    warnings: list[str]

    @field_validator('corners')
    @classmethod
    def must_have_corners(cls, v):
        if len(v) < 4:
            raise ValueError(f"Too few corners: {len(v)}. Minimum is 4.")
        return v

    @field_validator('components')
    @classmethod
    def must_have_components(cls, v):
        if len(v) < 1:
            raise ValueError("components list cannot be empty")
        return v

    @model_validator(mode='after')
    def segments_reference_valid_corners(self):
        labels = {c.label for c in self.corners}
        for seg in self.line_segments:
            if seg.end1 not in labels:
                raise ValueError(f"Segment {seg.number} end1='{seg.end1}' not in corners")
            if seg.end2 not in labels:
                raise ValueError(f"Segment {seg.number} end2='{seg.end2}' not in corners")
        return self

    @model_validator(mode='after')
    def origin_must_exist(self):
        xs = [c.x for c in self.corners]
        ys = [c.y for c in self.corners]
        if min(xs) > 0.1:
            raise ValueError(f"No corner at x=0. Min x is {min(xs)}. Origin rule violated.")
        if min(ys) > 0.1:
            raise ValueError(f"No corner at y=0. Min y is {min(ys)}. Origin rule violated.")
        return self


# ── Agent 3: Validator Output ─────────────────────────────────────────────────

class ValidatorOutput(BaseModel):
    valid: bool
    errors: list[str]        # empty if valid=True
    corrected_corners: Optional[list[Corner]] = None   # if validator can fix minor issues