"""
geometry/determinacy.py
-----------------------
Deterministic invalid-image detector. It does NOT trust the model's self-report.

Idea: a drawing is VALID (fully dimensioned, no assumptions) iff every distinct
coordinate of the geometry can be tied back to the origin through a spanning set
of EXPLICIT dimensions - one dimension consumed per independent gap. If, after
using every explicit dimension, some coordinate is still floating, that position
was assumed (symmetry / centering / "same plate bent") and the image is invalid.

We run this per axis:
  x-coordinates (vertical edges)  must be spanned by horizontal dimensions
  y-coordinates (horizontal edges) must be spanned by vertical dimensions

Each explicit dimension is a single constraint and may be consumed once. This is
exactly the difference between "the dimensions DETERMINE the geometry" (valid)
and "the geometry is merely CONSISTENT with the dimensions" (could be assumed).
"""

from collections import defaultdict

TOL = 1.0


def _coords_from_components(components):
    xs, ys = set(), set()
    edge_owner_x = defaultdict(list)  # x-value -> [(component_name, side)]
    edge_owner_y = defaultdict(list)
    for c in components:
        x0, x1 = c["bottomX"], c["bottomX"] + c["breadth"]
        y0, y1 = c["bottomY"], c["bottomY"] + c["depth"]
        xs.add(round(x0, 3)); xs.add(round(x1, 3))
        ys.add(round(y0, 3)); ys.add(round(y1, 3))
        edge_owner_x[round(x0, 3)].append((c["name"], "left"))
        edge_owner_x[round(x1, 3)].append((c["name"], "right"))
        edge_owner_y[round(y0, 3)].append((c["name"], "bottom"))
        edge_owner_y[round(y1, 3)].append((c["name"], "top"))
    return sorted(xs), sorted(ys), edge_owner_x, edge_owner_y


def _split_dims_by_axis(labeled_dimensions, xs, ys):
    """Return (h_values, v_values). Uses explicit axis tag when present, else
    infers from the dimension's location text, else from which coordinate
    differences the value matches uniquely."""
    h_vals, v_vals = [], []
    x_diffs = {round(abs(a - b), 3) for a in xs for b in xs if abs(a - b) > TOL}
    y_diffs = {round(abs(a - b), 3) for a in ys for b in ys if abs(a - b) > TOL}
    for d in labeled_dimensions:
        v = float(d["value"])
        axis = (d.get("axis") or "").lower()
        loc = (d.get("location") or "").lower()
        name = (d.get("name") or "").lower()
        if axis in ("h", "horizontal", "x"):
            h_vals.append(v); continue
        if axis in ("v", "vertical", "y"):
            v_vals.append(v); continue
        # infer from text
        if "horizontal" in loc or "width" in name:
            h_vals.append(v); continue
        if "vertical" in loc or "height" in name or "thickness" in name:
            # thickness can be either; fall through to geometry test if ambiguous
            if "height" in name or "vertical" in loc:
                v_vals.append(v); continue
        # infer from geometry: does it match an x-diff, a y-diff, or both?
        mx = any(abs(v - dx) <= TOL for dx in x_diffs)
        my = any(abs(v - dy) <= TOL for dy in y_diffs)
        if mx and not my:
            h_vals.append(v)
        elif my and not mx:
            v_vals.append(v)
        else:
            # ambiguous: contribute to both pools (conservative - easier to be
            # 'determined'; a genuinely missing dim still won't have any match)
            h_vals.append(v); v_vals.append(v)
    return h_vals, v_vals


def _span(coords, values):
    """Consumable union-find: try to connect all coords using each value once.
    Returns the set of coords NOT connected to the component holding min(coords)."""
    if len(coords) <= 1:
        return set()
    parent = {c: c for c in coords}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
            return True
        return False

    remaining = list(values)
    progress = True
    while progress and remaining:
        progress = False
        for v in list(remaining):
            done = False
            for i in range(len(coords)):
                for j in range(i + 1, len(coords)):
                    if abs(abs(coords[i] - coords[j]) - v) <= TOL and find(coords[i]) != find(coords[j]):
                        union(coords[i], coords[j])
                        remaining.remove(v)
                        progress = done = True
                        break
                if done:
                    break

    anchor = find(min(coords))
    return {c for c in coords if find(c) != anchor}


def check_determinacy(components, labeled_dimensions) -> dict:
    """Returns {determined: bool, reason: str|None, floating: [...]}"""
    if not components:
        return {"determined": False, "reason": "no components to check", "floating": []}

    xs, ys, own_x, own_y = _coords_from_components(components)
    h_vals, v_vals = _split_dims_by_axis(labeled_dimensions, xs, ys)

    float_x = _span(xs, h_vals)
    float_y = _span(ys, v_vals)

    if not float_x and not float_y:
        return {"determined": True, "reason": None, "floating": []}

    parts = []
    for x in sorted(float_x):
        who = ", ".join(f"{n}.{s}" for n, s in own_x.get(x, [])) or f"x={x:g}"
        parts.append(f"horizontal position of {who} (x={x:g}) is not fixed by any explicit width/offset dimension")
    for y in sorted(float_y):
        who = ", ".join(f"{n}.{s}" for n, s in own_y.get(y, [])) or f"y={y:g}"
        parts.append(f"vertical position of {who} (y={y:g}) is not fixed by any explicit height/thickness dimension")

    reason = ("This drawing is under-constrained - the following cannot be "
              "derived from the labeled dimensions by arithmetic alone (no "
              "symmetry/centering/uniform-thickness assumption is applied): "
              + "; ".join(parts) + ". Add the missing dimension(s).")
    return {"determined": False, "reason": reason,
            "floating": [f"x={x:g}" for x in sorted(float_x)] + [f"y={y:g}" for y in sorted(float_y)]}