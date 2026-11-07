# Structural Geometry Extraction Pipeline — Project Context

---

## 1. Project Purpose

This project extracts structural geometry from engineering section drawings and converts them into deterministic machine-readable representations.

The extracted geometry is intended to support downstream engineering workflows including:

- Centroid calculation
- Moment of inertia calculation
- Section property computation
- Structural analysis
- Joint and connection design
- Wall attachment analysis
- Design optimization
- CAD and reporting workflows

> The goal is not simply to recognize shapes.
> The goal is to reconstruct the structural section in a form that can be analyzed, modified, and used for engineering decision making.

---

## 2. Why Geometry Extraction Matters

The system must identify:

- Exact coordinates
- Exact boundary geometry
- Structural components
- Component dimensions
- Component locations

This information allows future systems to answer questions such as:

- Where should a structural joint be placed?
- How should a member connect to a wall?
- How does changing flange width affect section properties?
- How does web thickness affect moment of inertia?
- How can the section be optimized while maintaining performance?

Accurate geometry is the foundation for all downstream calculations.

---

## 3. Current Architecture (4-Agent Pipeline)

```
Observer (Perception) → Inferencer (Geometry) → Validator (Auditing) → Joint Placement (Detection)
```

### 1. Observer Agent
Pure observation. No calculations or inferences.

**Responsibilities:**
- Read dimensions
- Read labels
- Identify section type
- Describe topology

### 2. Inferencer Agent
Geometry reconstruction.

**Responsibilities:**
- Derive arithmetic dimensions
- Build coordinate system
- Generate coordinates
- Generate line segments
- Generate structural components

### 3. Validator Agent
Geometry auditing.

**Responsibilities:**
- Verify dimensions
- Verify placement
- Verify consistency
- Verify geometry correctness

### 4. Joint Placement Agent
Joint detection from red marker lines.

**Responsibilities:**
- Detect all red marker lines
- Map each red line to start and end coordinates
- Output joints in the same coordinate system
- Do NOT place joints at 90° bends (corners)

---

## 4. Engineering Philosophy

The system should behave as a **deterministic geometry calculator**.

**Allowed:**
- Explicit dimensions
- Arithmetic derived from explicit dimensions

**Not Allowed:**
- Symmetry assumptions
- Centerline assumptions
- Drafting convention assumptions
- Visual estimation
- Engineering intuition

---

## 5. Handling Underconstrained Geometry

The primary objective is accurate geometry extraction.
However, geometry that cannot be uniquely determined must not be guessed.

If coordinates require assumptions rather than explicit dimensions or arithmetic derivation, the image should be reported as invalid.

This rule exists to protect downstream engineering calculations from incorrect geometry.
Invalid-image detection is therefore a reliability feature, not the primary product objective.

---

## 6. Current Working Output

The pipeline returns a single JSON object with the following top-level structure:

```json
{
  "analysis": {
    "section_type": "...",
    "unit": "...",
    "dimensions_read": { ... },
    "corners": [
      { "label": "A", "x": 0.0, "y": 0.0 },
      { "label": "B", "x": 20.0, "y": 0.0 }
    ],
    "line_segments": [
      { "id": 1, "end1": "A", "end2": "B" }
    ],
    "components": [
      { "name": "top_flange", "bottomX": 0.0, "bottomY": 20.0, "breadth": 200.0, "depth": 20.0 }
    ],
    "joints": [
      { "name": "J1", "start": { "x": 10.0, "y": 90.0 }, "end": { "x": 30.0, "y": 90.0 } }
    ],
    "assumptions": [ "..." ],
    "warnings": [ "..." ]
  }
}
```

### Output Field Reference

| Key | Description |
|-----|-------------|
| `section_type` | Detected section type (e.g., I-beam, channel, T-section, compound) |
| `unit` | Unit detected from drawing (e.g., mm) or "unspecified" |
| `dimensions_read` | All dimensions explicitly read from the drawing |
| `corners` | All corner points with labels and coordinates (x, y) |
| `line_segments` | All boundary line segments by corner endpoints |
| `components` | Decomposed structural components with location and size |
| `joints` | All joints from red marker lines with start and end coordinates |
| `assumptions` | Any assumptions made due to underconstrained geometry |
| `warnings` | Any warnings including determinacy or validity issues |

---

## 7. Long-Term Direction

The extracted JSON should eventually serve as the source of truth for:

- Structural calculations
- Visualization
- Interactive editing
- Optimization workflows

**Preferred architecture:**

```
Image → LLM Perception Layer → Geometry Extraction → Deterministic Python Geometry Engine → Engineering Calculations / Interactive Visualization
```

The long-term goal is to use LLMs primarily for perception tasks and use deterministic code for geometry, calculations, and analysis.

---

## 8. Current Development Priorities

1. Improve geometry reconstruction accuracy.
2. Eliminate hidden assumptions.
3. Detect underconstrained geometry.
4. Improve component extraction.
5. Improve joint detection robustness (red markers).
6. Improve frontend visualization.
7. Support future engineering calculations and design workflows.

---

## Joint Specification (Red Marker)

Joints are specified using red marker lines on the drawing. Each red line represents a structural joint location.

### Rules:
- A red line may be horizontal or vertical.
- Joints are always placed on members, not in free space.
- Multiple red lines = multiple joints.
- Each red line corresponds to ONE joint only.
- The endpoints of the red line define the joint start and end in the same coordinate system as the geometry.

### Important Exclusion:
Joints are **NOT** placed at 90° bends (inside or outside corners) of the structure. A joint at a corner would be both horizontal and vertical, which is not allowed.

---

## Notes

- The pipeline returns **ONLY JSON**. No Excel, DXF, or other exports are generated.
- All coordinates are in the same 2D Cartesian system derived by the Inferencer Agent.
- The system is designed for CAD-style structural section drawings with dimensions and red joint markers.