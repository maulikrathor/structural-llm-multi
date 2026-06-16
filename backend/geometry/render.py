"""
geometry/render.py
------------------
Two pure-Python, zero-LLM steps that run after solver.solve() succeeds:

  build_geometry(coords) -> corners (clockwise, labeled A,B,C...),
                            line_segments, components
      Uses shapely to union the member rectangles into the outline, so
      re-entrant corners and notches fall out automatically - no manual
      traversal reasoning, no hallucination.

  render(corners, components, ...) -> PNG bytes
      Redraws the section to scale with each corner labeled A,B,C... placed
      just OUTSIDE the outline, an optional coordinate table, and translucent
      shaded/named components - this is the image the frontend shows the user
      so they know the nomenclature.
"""

import io
import string

from shapely.geometry import box
from shapely.ops import unary_union
from shapely.geometry.polygon import orient


def _clean_collinear(pts, tol=1e-6):
    """Drop vertices that lie on a straight line between their neighbours,
    so every kept point is a real direction change (a corner)."""
    n = len(pts)
    out = []
    for i in range(n):
        ax, ay = pts[(i - 1) % n]
        bx, by = pts[i]
        cx, cy = pts[(i + 1) % n]
        cross = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
        if abs(cross) > tol:
            out.append((round(bx, 6), round(by, 6)))
    return out


def build_geometry(coords: dict[str, dict[str, float]]):
    """coords: rect_name -> {left,right,bottom,top}. Returns (corners, segments, components)."""
    rects = [box(c["left"], c["bottom"], c["right"], c["top"]) for c in coords.values()]
    merged = unary_union(rects)
    if merged.geom_type != "Polygon":
        raise ValueError(f"members do not form one connected region ({merged.geom_type})")

    ring = orient(merged, sign=-1.0)             # sign=-1 -> clockwise exterior
    pts = list(ring.exterior.coords)[:-1]        # drop closing duplicate
    pts = _clean_collinear(pts)

    # rotate so labelling starts at the top-left-most corner (highest y, then lowest x)
    start = min(range(len(pts)), key=lambda i: (-pts[i][1], pts[i][0]))
    pts = pts[start:] + pts[:start]

    labels = _labels(len(pts))
    corners = [{"label": labels[i], "x": x, "y": y} for i, (x, y) in enumerate(pts)]

    n = len(corners)
    segments = [{"number": i + 1, "end1": corners[i]["label"],
                 "end2": corners[(i + 1) % n]["label"]} for i in range(n)]

    components = [{"name": name, "bottomX": c["left"], "bottomY": c["bottom"],
                   "breadth": c["right"] - c["left"], "depth": c["top"] - c["bottom"]}
                  for name, c in coords.items()]
    return corners, segments, components


def _labels(n):
    """A,B,...,Z,AA,AB,... for any corner count."""
    out, alpha = [], string.ascii_uppercase
    for i in range(n):
        s, k = "", i
        while True:
            s = alpha[k % 26] + s
            k = k // 26 - 1
            if k < 0:
                break
        out.append(s)
    return out


def render(corners, components, *, section_type="", unit="", show_coords=True) -> bytes:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    xs = [c["x"] for c in corners]
    ys = [c["y"] for c in corners]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    diag = max((max(xs) - min(xs)), (max(ys) - min(ys))) or 1.0
    pad = diag * 0.12

    fig, ax = plt.subplots(figsize=(7, 7))

    # filled outline
    ax.fill(xs + [xs[0]], ys + [ys[0]], facecolor="#cfe8d4",
            edgecolor="#1f7a3d", linewidth=2.0, zorder=1)

    # translucent named components
    palette = ["#4477aa", "#ee6677", "#228833", "#ccbb44", "#aa3377", "#66ccee"]
    for i, comp in enumerate(components):
        ax.add_patch(Rectangle((comp["bottomX"], comp["bottomY"]),
                               comp["breadth"], comp["depth"],
                               facecolor=palette[i % len(palette)], alpha=0.18,
                               edgecolor="none", zorder=2))
        ax.text(comp["bottomX"] + comp["breadth"] / 2,
                comp["bottomY"] + comp["depth"] / 2, comp["name"],
                ha="center", va="center", fontsize=7.5, color="#333", zorder=3,
                style="italic")

    # corner labels placed OUTSIDE the outline (direction = centroid -> vertex)
    for c in corners:
        dx, dy = c["x"] - cx, c["y"] - cy
        norm = (dx * dx + dy * dy) ** 0.5 or 1.0
        lx = c["x"] + dx / norm * pad
        ly = c["y"] + dy / norm * pad
        ax.plot(c["x"], c["y"], "o", color="#1f7a3d", markersize=4, zorder=4)
        txt = c["label"]
        if show_coords:
            txt += f"\n({c['x']:g}, {c['y']:g})"
        ax.text(lx, ly, txt, ha="center", va="center", fontsize=8.5,
                fontweight="bold", color="#11401f", zorder=5,
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#1f7a3d", lw=0.8))

    title = section_type or "section"
    if unit:
        title += f"  (units: {unit})"
    ax.set_title(title, fontsize=11)
    ax.set_aspect("equal")
    ax.grid(True, linestyle=":", alpha=0.4)
    ax.set_xlim(min(xs) - pad * 1.6, max(xs) + pad * 1.6)
    ax.set_ylim(min(ys) - pad * 1.6, max(ys) + pad * 1.6)
    ax.set_xlabel("x"); ax.set_ylabel("y")

    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=140)
    plt.close(fig)
    return buf.getvalue()