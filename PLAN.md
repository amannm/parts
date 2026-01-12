# Implementation Plan: Parametric CAD → Semantic Tagging → Meshing → Multiphysics FEM → Reproducible Outputs

## 1) Objectives and scope
- Deliver a single Python runtime that runs CAD → mesh → solve → post, preserving semantic tags end-to-end.
- Provide config-driven orchestration with clean module contracts and reproducible outputs.
- Prefer in-memory Gmsh → DOLFINx handoff and VTX outputs; keep `.msh` import as debug/interop.
- Build an extensible physics registry (start with Poisson, add heat and elasticity).
- Track provenance, caching, and QA gates as first-class pipeline features.

Non-goals for v1:
- Full UI/GUI (CLI + Python API only).
- Adaptive remeshing loops (hooks only).
- Complex CAD feature provenance tagging beyond the basic TagSpec rule set.

## 2) Guiding decisions (from SPEC.md and design notes)
- D1: Single-runtime architecture (MPI only for solve).
- D2: Semantic tags defined by rules (TagSpec) and mapped to numeric IDs internally.
- D3: Physical groups in Gmsh are the canonical tag carrier.
- D4: `dolfinx.io.gmsh.model_to_mesh` is the default import path.
- D5: VTXWriter is default output; XDMF is fallback.

## 3) Target package layout
```
src/simstack/
  core/
    project.py        # Project/Study, DAG execution, caching hooks
    artifacts.py      # CadArtifact, MeshArtifact, SolveArtifact, PostArtifact
    registry.py       # physics registry + solver presets
    provenance.py     # version capture, config snapshot, hashing

  cad/
    build.py          # CadQuery builders
    tags.py           # TagSpec definitions + CAD helpers
    bridge.py         # STEP export (v1) + optional OCC pointer bridge (v2)

  mesh/
    tag_transfer.py   # TagSpec -> gmsh physical groups
    mesh_build.py     # sizing fields, BLs, QA, mesh generation
    import_dolfinx.py # model_to_mesh / read_from_msh

  fem/
    spaces.py
    materials.py
    coeffs.py
    bcs.py
    physics/
      poisson.py
      heat.py
      elasticity.py
    assemble.py
    solve.py

  io/
    write.py          # VTX/XDMF writers + mesh/tag outputs
    paraview.py       # pvsm templates

  cli.py              # config-first entry point
  config.py           # config schema + validation
```

## 4) Implementation phases

### Phase 0 — Foundations (repo + config spine)
Work items:
- Create `pyproject.toml` with `uv`-friendly dependency groups.
- Add `src/simstack` package and minimal `cli.py`.
- Implement config schema (pydantic or dataclasses + validators).
- Implement `core/artifacts.py` data models and `core/provenance.py` hashing helpers.
- Add logging + structured run reports (JSON).

Deliverables:
- `pyproject.toml`, `src/simstack/config.py`, `src/simstack/cli.py`.
- `core/artifacts.py`, `core/provenance.py`.

Exit criteria:
- `simstack run config.yaml` loads config and logs a dry-run plan.

---

### Phase 1 — Hello pipeline (M1)
Work items:
- CadQuery: implement a simple builder (block with hole) in `cad/build.py`.
- TagSpec v1 rules: `PlaneAtMin`, `PlaneAtMax`, `AllVolumes` in `cad/tags.py`.
- Meshing: import STEP into Gmsh, generate mesh, add physical groups for the two planes and a single volume.
- DOLFINx import: implement `model_to_mesh` path; keep `.msh` import for debugging.
- FEM: implement Poisson model (scalar CG1), DG0 material field, two Dirichlet BCs.
- IO: write VTX output and `solve_report.json`.

Deliverables:
- `cad/build.py`, `cad/tags.py`, `mesh/mesh_build.py`, `mesh/import_dolfinx.py`.
- `fem/physics/poisson.py`, `fem/solve.py`, `io/write.py`.
- `examples/configs/hello.yaml` (or similar).

Exit criteria:
- End-to-end run produces mesh tags and a VTX result; ParaView can load it.

---

### Phase 2 — Tagging system + QA gates (M2)
Work items:
- Expand TagSpec rule vocabulary: `NormalApprox`, `BBoxPatch`, `AllExcept`.
- Implement TagSpec evaluation on Gmsh entities (centroids, normals, bbox checks).
- Deterministic numeric ID policy with collision handling; store `tag_map.json`.
- Mesh QA gate: min quality, tag coverage checks, contiguity where applicable.

Deliverables:
- `mesh/tag_transfer.py` with robust rule evaluation.
- `core/provenance.py` updated to include tag map + mesh stats.
- `mesh/mesh_build.py` includes QA checks and report output.

Exit criteria:
- Tagging rules are stable across geometry changes; QA gates fail fast on missing tags.

---

### Phase 3 — Multi-material + coefficient fields (M2 continuation)
Work items:
- `fem/materials.py`: build MatDB from `cell_tags` names.
- `fem/coeffs.py`: DG0 coefficient fields; enforce robust mapping.
- Extend config schema to support multiple materials and map by tag name.

Deliverables:
- Multi-material Poisson example config.
- `reports/` includes material mapping validation output.

Exit criteria:
- Two+ materials with different coefficients solve correctly and are visible in output fields.

---

### Phase 4 — Heat + Elasticity modules (M3)
Work items:
- Implement `fem/physics/heat.py` (steady + optional transient).
- Implement `fem/physics/elasticity.py` (linear elasticity).
- Add Neumann/Robin BC support via `fem/bcs.py` and physics-specific natural terms.
- Add solver presets for nonlinear/transient runs in `core/registry.py`.

Deliverables:
- `physics/heat.py` and `physics/elasticity.py` + example configs.
- Solver report includes convergence reason, residual norms, timings.

Exit criteria:
- Heat and elasticity both run end-to-end with BCs based on facet tag names.

---

### Phase 5 — Project DAG + caching (M4)
Work items:
- Implement `core/project.py` with DAG nodes (Cad/Mesh/Solve/Post).
- Add ArtifactStore (hash-based) and `out/<hash>/` layout.
- `latest` pointer or symlink per study.
- Provenance report includes config snapshot, versions, git hash.

Deliverables:
- `core/project.py` + `core/artifacts.py` fully wired.
- `reports/provenance.json` and `reports/solve_report.json` per run.

Exit criteria:
- No-op runs reuse cached artifacts; provenance is reproducible across runs.

---

### Phase 6 — Output polish + ParaView integration (M4)
Work items:
- Default VTX output; XDMF optional.
- Write mesh tags as arrays for visualization (cell/facet tag IDs).
- Implement `io/paraview.py` to generate a `.pvsm` template that loads latest results.

Deliverables:
- `io/write.py` VTX + XDMF support.
- Optional `.pvsm` output for quick visualization.

Exit criteria:
- ParaView opens outputs without manual tag wiring; coloring by tag IDs works.

---

### Phase 7 — Tests and verification
Work items:
- Unit tests for TagSpec evaluation and tag transfer.
- Manufactured solution tests for Poisson/heat/elasticity.
- Regression test for mesh QA thresholds.

Deliverables:
- `tests/` covering TagSpec, Meshing, and Poisson solves.
- Optional CI configuration (if desired).

Exit criteria:
- Tests pass locally via `uv` and catch common regressions in tags/BCs.

## 5) Cross-cutting requirements
- Config-first orchestration; all stages consume validated config inputs.
- Strict separation of concerns: CAD/meshing/solve/io modules with narrow I/O contracts.
- Tag stability: BCs/materials only reference tag names, never raw IDs.
- Reproducible outputs: provenance, hashes, and versions recorded per run.
- Prefer in-memory Gmsh → DOLFINx; allow `.msh` path for debugging.

## 6) Acceptance checklist
- End-to-end run with stable tag names across CAD changes.
- Heat and elasticity produce VTX output and solver reports.
- Multi-material case works with DG0 coefficients.
- Provenance includes config snapshot + versions + tag_map.
- QA gates fail fast on missing tags or low-quality meshes.

## 7) Execution notes
- Use `uv` for Python installs, lockfiles, and test runs.
- Keep performance-sensitive sections (tag evaluation, mesh QA) isolated for future optimization.
- Favor deterministic outputs (hash-based IDs, sorted entity traversal) to ensure stable caching.
