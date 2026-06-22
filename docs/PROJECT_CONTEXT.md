# Structural Geometry Extraction Pipeline

## Project Purpose

This project extracts structural geometry from engineering section drawings and converts them into deterministic machine-readable representations.

The extracted geometry is intended to support downstream engineering workflows including:

* Centroid calculation
* Moment of inertia calculation
* Section property computation
* Structural analysis
* Joint and connection design
* Wall attachment analysis
* Design optimization
* CAD and reporting workflows

The goal is not simply to recognize shapes.

The goal is to reconstruct the structural section in a form that can be analyzed, modified, and used for engineering decision making.

---

# Why Geometry Extraction Matters

The system must identify:

* Exact coordinates
* Exact boundary geometry
* Structural components
* Component dimensions
* Component locations

This information allows future systems to answer questions such as:

* Where should a structural joint be placed?
* How should a member connect to a wall?
* How does changing flange width affect section properties?
* How does web thickness affect moment of inertia?
* How can the section be optimized while maintaining performance?

Accurate geometry is the foundation for all downstream calculations.

---

# Required Outputs

The system generates:

## Coordinates

A complete coordinate representation of the section boundary.

## Line Segments

A geometric boundary representation.

## Structural Components

Semantic decomposition of the structure into primitive elements.

Examples:

* top_flange
* bottom_flange
* central_web
* left_web
* right_web
* vertical_leg

Component extraction is critical because downstream engineering calculations often operate on components rather than only on boundary coordinates.

---

# Current Architecture

Observer → Inferencer → Validator

This is the approved architecture.

## Observer

Pure observation.

Responsibilities:

* Read dimensions
* Read labels
* Identify section type
* Describe topology

Must not calculate or infer.

## Inferencer

Geometry reconstruction.

Responsibilities:

* Derive arithmetic dimensions
* Build coordinate system
* Generate coordinates
* Generate line segments
* Generate structural components

## Validator

Geometry auditing.

Responsibilities:

* Verify dimensions
* Verify placement
* Verify consistency
* Verify geometry correctness

---

# Engineering Philosophy

The system should behave as a deterministic geometry calculator.

Allowed:

* Explicit dimensions
* Arithmetic derived from explicit dimensions

Not Allowed:

* Symmetry assumptions
* Centerline assumptions
* Drafting convention assumptions
* Visual estimation
* Engineering intuition

---

# Handling Underconstrained Geometry

The primary objective is accurate geometry extraction.

However, geometry that cannot be uniquely determined must not be guessed.

If coordinates require assumptions rather than explicit dimensions or arithmetic derivation, the image should be reported as invalid.

This rule exists to protect downstream engineering calculations from incorrect geometry.

Invalid-image detection is therefore a reliability feature, not the primary product objective.

---

# Frontend Vision

Frontend visualization is a critical part of the project.

Users should be able to:

* View extracted coordinates
* View structural components
* Understand topology
* Verify reconstruction accuracy

The long-term goal is to create an interactive representation of the extracted structure.

Potential capabilities include:

* Coordinate visualization
* Component highlighting
* Scaled rendering from extracted geometry
* Geometry editing
* Flange and web dimension modification
* Real-time property recalculation
* Design experimentation

The frontend should become a bridge between extracted geometry and engineering exploration.

---

# Long-Term Direction

The extracted JSON should eventually serve as the source of truth for:

* Structural calculations
* Visualization
* Interactive editing
* Optimization workflows

Preferred architecture:

Image
↓
LLM Perception Layer
↓
Geometry Extraction
↓
Deterministic Geometry Engine
↓
Engineering Calculations
↓
Interactive Visualization

The long-term goal is to use LLMs primarily for perception tasks and use deterministic code for geometry, validation, calculations, and analysis.

---

# Current Development Priorities

1. Improve geometry reconstruction accuracy.
2. Eliminate hidden assumptions.
3. Detect underconstrained geometry.
4. Improve component extraction.
5. Improve frontend visualization.
6. Support future engineering calculations and design workflows.
