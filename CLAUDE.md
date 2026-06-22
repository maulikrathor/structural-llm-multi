# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:

* State assumptions explicitly.
* If uncertain, ask.
* If multiple interpretations exist, present them.
* If a simpler approach exists, say so.
* If something is unclear, stop and ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

* No features beyond what was asked.
* No abstractions for single-use code.
* No configurability that wasn't requested.
* No premature optimization.
* If 200 lines can be 50, simplify.

Ask:

> Would a senior engineer consider this overengineered?

If yes, simplify.

## 3. Surgical Changes

**Touch only what you must.**

When editing existing code:

* Don't refactor unrelated code.
* Don't change formatting unnecessarily.
* Match the existing style.
* Mention unrelated issues, don't fix them.

When your changes create dead code:

* Remove code made obsolete by your changes.
* Do not remove unrelated dead code.

Every changed line should be traceable to the requested task.

## 4. Goal-Driven Execution

Transform tasks into verifiable goals.

For non-trivial tasks:

1. State the plan.
2. Identify files to change.
3. Implement.
4. Verify.
5. Summarize results.

Prefer measurable success criteria.

---

# Project Context

## Architecture

Current approved architecture:

Observer → Inferencer → Validator

This is the primary implementation.

Legacy single-agent implementations may exist for reference but are not the target system.

## Project Goal

Extract accurate structural geometry from engineering drawings.

Outputs include:

* Coordinates
* Line segments
* Structural components
* Machine-readable JSON

The extracted geometry is intended for downstream engineering calculations and visualization.

## Engineering Rules

Geometry may be derived only from:

1. Explicit dimensions
2. Arithmetic on explicit dimensions

Do not rely on:

* Symmetry assumptions
* Centerline assumptions
* Drafting conventions
* Visual estimation

If geometry cannot be uniquely determined, report missing constraints rather than inventing geometry.

## Deterministic First

Prefer deterministic Python logic over LLM reasoning whenever practical.

Use LLMs primarily for:

* OCR
* Shape recognition
* Topology understanding

Use code for:

* Arithmetic
* Validation
* Consistency checks
* Engineering calculations

## Frontend

Frontend visualization is a primary feature.

Users should be able to understand:

* Coordinates
* Components
* Structural topology

Prioritize interpretability over visual complexity.

## Additional Context

For architecture details, business context, roadmap, and examples:

Read:

* docs/PROJECT_CONTEXT.md

before making significant architectural changes.
