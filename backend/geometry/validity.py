"""
geometry/validity.py
--------------------
Deterministic invalid-image gate for the 3-agent pipeline.

The Inferencer now emits a structured `assumptions` list: every position it
could NOT determine from explicit dimensions + arithmetic (i.e. it would have
had to assume symmetry / centering / visual alignment). This module turns that
local, factual self-report into the verdict - the LLM never decides valid/invalid
itself, which is what makes the gate reliable and stops valid images being
wrongly rejected.

Rule: assumptions present  -> INVALID (name the missing dimension).
      assumptions empty     -> VALID, then run pure-code consistency checks.
"""

from shapely.geometry import box, Polygon
from shapely.ops import unary_union

TOL = 0.5


def _consistency_checks(corners, components) -> list[str]:
    warns = []
    if not corners:
        return ["no corners produced"]

    xs = [c["x"] for c in corners]
    ys = [c["y"] for c in corners]
    if abs(min(xs)) > TOL:
        warns.append(f"origin: smallest x is {min(xs):g}, expected 0")
    if abs(min(ys)) > TOL:
        warns.append(f"origin: smallest y is {min(ys):g}, expected 0")
    if min(xs) < -TOL or min(ys) < -TOL:
        warns.append("negative coordinates present")

    # components should tile the outline polygon with no gaps/overlap
    if components and len(corners) >= 3:
        try:
            outline = Polygon([(c["x"], c["y"]) for c in corners])
            comp = unary_union([box(c["bottomX"], c["bottomY"],
                                    c["bottomX"] + c["breadth"],
                                    c["bottomY"] + c["depth"]) for c in components])
            if outline.area > 0:
                missing = outline.area - comp.intersection(outline).area
                extra = comp.area - comp.intersection(outline).area
                if abs(missing) > max(TOL, 0.02 * outline.area):
                    warns.append(f"components leave {missing:g} of the section uncovered")
                if abs(extra) > max(TOL, 0.02 * outline.area):
                    warns.append(f"components overlap or exceed the section by {extra:g}")
        except Exception as e:
            warns.append(f"could not verify component tiling: {e}")
    return warns


def assess_validity(inferencer: dict) -> dict:
    """Turn the Inferencer output into a valid/invalid verdict."""
    assumptions = inferencer.get("assumptions") or []
    corners = inferencer.get("corners", []) or []
    components = inferencer.get("components", []) or []
    segments = inferencer.get("line_segments", []) or []
    warnings = list(inferencer.get("warnings", []) or [])

    if assumptions:
        parts = []
        for a in assumptions:
            feat = a.get("feature", "a position")
            need = a.get("needed_dimension", "an additional dimension")
            parts.append(f"{feat} (needs: {need})")
        reason = ("This drawing is under-constrained - the following cannot be "
                  "determined from the labeled dimensions by arithmetic alone, and "
                  "no assumption (symmetry, centering, alignment) is permitted: "
                  + "; ".join(parts) + ".")
        return {"valid": False, "reason": reason,
                "corners": [], "line_segments": [], "components": [],
                "warnings": warnings}

    warnings += _consistency_checks(corners, components)
    return {"valid": True, "reason": None,
            "corners": corners, "line_segments": segments,
            "components": components, "warnings": warnings}