"""
geometry/finalize.py
--------------------
Call this in pipeline.build_output AFTER the Inferencer/Validator. It runs the
DETERMINISTIC determinacy gate (geometry/determinacy.py - does not trust the
model's self-report) and, for valid sections, the matplotlib render. Returns the
final dict your frontend consumes (your existing corners/line_segments/components
shape, plus valid / reason / render_png_base64 / warnings).
"""

import base64

from geometry.determinacy import check_determinacy
from geometry.validity import _consistency_checks
from geometry.render import render, build_geometry


def finalize(observation: dict, inference: dict, *,
             section_type: str = "", unit: str = "",
             rebuild_geometry: bool = False) -> dict:
    components = inference.get("components", []) or []
    corners = inference.get("corners", []) or []
    segments = inference.get("line_segments", []) or []
    labeled = observation.get("labeled_dimensions", []) or []
    warnings = list(inference.get("warnings", []) or [])

    base = {
        "valid": True, "reason": None,
        "section_type": section_type or inference.get("section_type"),
        "unit": unit or inference.get("unit"),
        "dimensions_read": inference.get("dimensions_read", {}),
        "corners": corners, "line_segments": segments, "components": components,
        "warnings": warnings, "render_png_base64": None,
    }

    # 1) deterministic determinacy gate (the authority)
    det = check_determinacy(components, labeled)
    if not det["determined"]:
        base.update(valid=False, reason=det["reason"],
                    corners=[], line_segments=[], components=[])
        return base

    # 2) optional clean rebuild of corners/segments from components
    if rebuild_geometry and components:
        try:
            coords = {c["name"]: {"left": c["bottomX"], "right": c["bottomX"] + c["breadth"],
                                  "bottom": c["bottomY"], "top": c["bottomY"] + c["depth"]}
                      for c in components}
            corners, segments, components = build_geometry(coords)
            base.update(corners=corners, line_segments=segments, components=components)
        except Exception as e:
            warnings.append(f"geometry rebuild skipped: {e}")

    # 3) pure-code consistency warnings (non-fatal)
    base["warnings"] = warnings + _consistency_checks(corners, components)

    # 4) render
    png = render(corners, components, section_type=base["section_type"] or "", unit=base["unit"] or "")
    base["render_png_base64"] = base64.b64encode(png).decode("ascii")
    return base