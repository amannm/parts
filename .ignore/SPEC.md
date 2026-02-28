## System specification: Parametric CAD → semantic tagging → meshing → multiphysics FEM → reproducible outputs

### 1) Purpose and scope

Build a **single Python system** that turns **parametric CAD** into a **tag-stable, solver-ready mesh**, runs one or more **DOLFINx/UFL/PETSc** physics models, and writes **ParaView-friendly results**—with strong emphasis on:

* **Semantic tags survive the whole pipeline** (BCs/materials attach to *names*, not fragile face indices). 
* **Config-driven orchestration** with clean module contracts (each pipeline “box” has a narrow I/O). 
* **Project DAG + caching + provenance** for reproducibility and fast iteration. 
* Prefer **in-memory Gmsh→DOLFINx** where possible and treat **VTX output as first-class**. 

This is intentionally designed as a “core engine” that can later grow a UI, parameter sweeps, and adaptive remeshing.

---

### 2) Primary design decisions (what the system commits to)

**D1. Single-runtime architecture**
A single Python process owns the end-to-end run (with MPI for solve). 

**D2. Tags are semantic names + rules**
Users define *rules* (TagSpec) for boundaries/subdomains; the system generates/maintains numeric IDs only as an implementation detail. 

**D3. Mesh tags are Physical Groups**
All boundary/subdomain tags are represented as **Gmsh Physical Groups** (with names), which DOLFINx can import as MeshTags. ([gmsh.info][1])

**D4. In-memory mesh handoff is the default**
The preferred path uses `dolfinx.io.gmsh.model_to_mesh(...)`, which processes the Gmsh model on one MPI rank and distributes the DOLFINx mesh.  ([FEniCS Project][2])

**D5. Output defaults to VTX**
Use `VTXWriter` by default (scalable; supports arbitrary order/discontinuous fields), with XDMF as a fallback/convenience format.  ([FEniCS Project][3])

---

### 3) External dependencies

Required (core run):

* **CadQuery** for parametric CAD; STEP export supported. ([cadquery.readthedocs.io][4])
* **Gmsh Python API** for geometry import + physical groups + meshing. ([gmsh.info][1])
* **DOLFINx + UFL** for FEM assembly and forms. ([FEniCS Project][5])
* **PETSc via petsc4py** (linear/nonlinear/transient solver backends). 
* **MPI via mpi4py** for distributed solve.

Recommended:

* `pydantic` for config validation and friendlier error messages. 
* ADIOS2 (transitively used for VTXWriter in many builds), depending on your DOLFINx install. ([FEniCS Project][3])

---

### 4) Conceptual model

#### 4.1 Project DAG

Every run is a DAG of typed artifacts with hashable inputs: 

* **CAD node**: params → shape + TagSpec metadata
* **Mesh node**: CAD + meshing config + TagSpec → gmsh model + mesh + physical groups
* **Solve node**: mesh + physics + materials + BCs + solver config → fields + diagnostics
* **Post node**: fields + tags → VTX/XDMF + metadata (+ optional ParaView state)

#### 4.2 Artifacts (typed outputs of each stage)

* `CadArtifact`: `shape_ref`, `step_path?`, `tag_spec`, `bbox`, `units`, `cad_provenance`
* `MeshArtifact`: `gmsh_model_ref`, `dolfinx_mesh`, `cell_tags`, `facet_tags`, `tag_map`, `mesh_stats`
* `SolveArtifact`: `fields`, `derived_fields`, `solver_report`, `timings`
* `PostArtifact`: `vtx_paths/xmf_paths`, `provenance_json`, `pvsm_path?`

---

### 5) Semantic tagging subsystem (TagSpec)

#### 5.1 Requirements

* Tags must be defined by **geometric predicates** and/or **construction provenance**, not face indices. 
* Tags apply to both:

  * **facets** (boundaries) for BCs
  * **cells** (volumes) for materials/subdomains

#### 5.2 TagSpec rule vocabulary (minimum viable set)

Facet rules:

* `PlaneAtMin(axis)`, `PlaneAtMax(axis)` (e.g., x=xmin is “inlet”) 
* `NormalApprox(nx,ny,nz,tol)`
* `BBoxPatch(xmin,xmax,...)`
* `AllExcept([...])`

Cell rules:

* `AllVolumes()` (v1)
* `Containment(test_shape)` / `InsideBBox(...)` (v2)
* `ByCADFeature(feature_id)` (optional advanced)

#### 5.3 Numeric ID policy

* Default: deterministic IDs derived from tag names (stable hash → int), stored in `tag_map.json`.
* Allow override via explicit IDs (useful when interfacing with legacy pipelines) similar to the `tag_schema` approach. 
* Collision handling: deterministic rehash/linear-probe within a reserved range per tag kind.

#### 5.4 Tag transfer: TagSpec → Gmsh Physical Groups

The mesher evaluates TagSpec on Gmsh entities (via bounding boxes, centroids, normals where available) and creates named physical groups.  ([gmsh.info][1])

---

### 6) Meshing subsystem (Gmsh)

#### 6.1 Responsibilities

The mesher must: 

* Import CAD (STEP as the v1 bridge; CadQuery supports STEP export).  ([cadquery.readthedocs.io][4])
* Apply sizing:

  * global size
  * curvature refinement
  * distance-to-tag refinement
  * optional boundary layers on selected facet tags
* Create physical groups for:

  * **cells**: materials/subdomains
  * **facets**: BC regions
* Run mesh QA gates:

  * quality histograms / min quality thresholds
  * boundary contiguity checks
  * “all boundary facets tagged exactly once” (policy configurable) 

#### 6.2 Parallelism model

* Gmsh generation typically happens on **rank 0**; then DOLFINx mesh is distributed. 
* `model_to_mesh` explicitly supports this “rank 0 builds, distribute afterwards” workflow. ([FEniCS Project][2])

---

### 7) Mesh import subsystem (DOLFINx)

Two supported import paths:

**Path A (preferred): In-memory Gmsh model → DOLFINx**

* Use `dolfinx.io.gmsh.model_to_mesh(model, comm, rank, gdim)` producing distributed mesh + tags.  ([FEniCS Project][2])

**Path B (debug/interop): `.msh` → DOLFINx**

* Use `dolfinx.io.gmshio.read_from_msh(...)` which returns `(mesh, cell_tags, facet_tags)` based on physical groups in the file. ([FEniCS Project][6])

Both paths must preserve a `tag_map` of `{name -> id, kind -> facet/cell}`.

---

### 8) FEM modeling subsystem (DOLFINx/UFL)

#### 8.1 Space & measure creation

* Build function spaces (scalar/vector/mixed), trial/test functions, and `dx/ds` measures indexed by MeshTags.

#### 8.2 Materials and coefficients

* `MatDB` maps **cell tag name → parameter dict** (human-readable). 
* Build coefficient fields from `cell_tags`:

  * v1: DG0 piecewise constants (fast, robust). 
  * v2+: projected/interpolated fields, tensors, nonlinear laws.

#### 8.3 BC specification and construction

* BCs reference **facet tag names** (never raw integers). 
* Support:

  * Dirichlet (strong)
  * Neumann/Robin (natural terms in forms) 

#### 8.4 Physics plugin interface (extensible registry)

Physics models are pluggable via a registry pattern. 

**Required interface (per module):**

* `declare_fields(config) -> FieldSpec[]`
* `build_spaces(mesh, field_spec, config) -> SpaceBundle`
* `build_coefficients(mesh, cell_tags, matdb, config) -> CoeffBundle`
* `build_bcs(V, facet_tags, config) -> (dirichlet_bcs, natural_terms)`
* `build_forms(spaces, coeffs, measures, config) -> (a, L) or (F, J)`
* `outputs(fields, coeffs, config) -> DerivedField[]`

This supports your “Poisson now, elasticity later” progression without refactoring the pipeline. 

---

### 9) Solve subsystem (PETSc)

#### 9.1 Solve modes

* Linear solve (KSP)
* Nonlinear solve (SNES)
* Transient solve (TS) 

#### 9.2 Solver configuration

* Solver options are **config-first**, with named presets that can be overridden per Study (e.g., `linear_default`, `nonlinear_newton`, `fieldsplit_stokes`). 
* Always record:

  * final PETSc options used
  * iteration counts, residual norms, convergence reason
  * timing breakdown

---

### 10) I/O and postprocessing

#### 10.1 Output policy

* Default: **VTXWriter** (ParaView-viewable; supports arbitrary order/discontinuous). ([FEniCS Project][3])
* Fallback: XDMF (handy and common for low-order geometry). ([FEniCS Project][3])

#### 10.2 Required outputs per run

* `mesh/` : mesh + `cell_tags` + `facet_tags`
* `fields/` : primary solution + derived fields
* `reports/solve_report.json` : solver diagnostics
* `reports/provenance.json` : config snapshot + versions + git hash + tag_map
* Optional: `.pvsm` ParaView state template for “load-and-go” visualization. 

---

### 11) Configuration schema (single source of truth)

A single validated config object drives every stage. 

**Key sections (minimum):**

* `geometry`: CAD builder name + parameters
* `tags`: TagSpec rules for facets/cells
* `meshing`: sizing strategy, boundary layers, QA thresholds
* `materials`: per cell tag name
* `physics`: model selection + PDE parameters
* `bcs`: per facet tag name
* `solver`: PETSc preset + overrides
* `outputs`: VTX/XDMF selection, directories, what to write

(You can keep a `tag_schema` override section for explicit IDs, matching the earlier pipeline-style config. )

---

### 12) Reference package layout (module boundaries)

This is the “flowchart → modules” mapping, wrapped in a Project/DAG shell. 

```
src/simstack/
  core/
    project.py        # Project, Study, DAG execution, caching
    artifacts.py      # CadArtifact, MeshArtifact, SolveArtifact, PostArtifact
    registry.py       # physics/bc/material registries, solver presets
    provenance.py     # versions, config snapshot, hashing

  cad/
    build.py          # CadQuery builders
    tags.py           # TagSpec definitions + CAD-side helpers
    bridge.py         # STEP export (v1) + optional OCC-pointer bridge (v2)

  mesh/
    tag_transfer.py   # TagSpec -> gmsh physical groups
    mesh_build.py     # size fields, BLs, QA, mesh generation
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
    write.py          # VTX/XDMF writers
    paraview.py       # pvsm templates
```

---

### 13) Caching, provenance, and QA gates

#### 13.1 ArtifactStore (content-addressed)

* Hash inputs per stage:

  * CAD hash = geometry params + builder version
  * Mesh hash = CAD hash + meshing params + TagSpec
  * Solve hash = mesh hash + physics + materials + BCs + solver params 
* Store artifacts under `out/<hash>/...` and maintain a “latest” pointer. 

#### 13.2 QA gates

* CAD gate: non-empty solids; expected tag rules resolve to non-empty entity sets
* Tag gate: every required tag name found; no unexpected overlaps unless allowed
* Mesh gate: quality thresholds, boundary contiguity, tag coverage
* Solve gate: convergence checks; conservation/energy checks (model-dependent)

#### 13.3 Verification strategy

* Unit tests for TagSpec evaluation and tag transfer
* Manufactured-solution tests for core physics modules
* Regression tests on mesh size/QoIs 

---

### 14) Public API (what “using the system” looks like)

Two supported entry styles:

**(A) CLI / config-first** (the “spine”) 

* `simstack run config.yaml`
* `simstack sweep sweep.yaml` (optional extension)

**(B) Python API**
A Project object that owns params, DAG, caching, and provenance. 
Example pattern appears in your notes (CAD model + tags + mesher + physics + solver). 

---

### 15) Build plan (practical milestone path)

This aligns with your “fast path to v1” plan. 

**M1 — Hello pipeline**

* CadQuery block-with-hole
* TagSpec: `left/right` via plane rules
* Gmsh physical groups for 1 volume + 2 faces
* DOLFINx Poisson + 2 Dirichlet BCs
* Output VTX + solve report

**M2 — Multi-material + robust tagging**

* 2+ cell tags; DG0 coefficient field from `cell_tags`
* Tag coverage + contiguity QA gate

**M3 — Second physics module**

* Linear elasticity or transient heat; Neumann/Robin support by facet tag

**M4 — Engineering UX**

* ArtifactStore hashing + provenance
* ParaView `.pvsm` generation
* Stable plugin registry and solver presets

---