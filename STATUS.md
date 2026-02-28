# SimStack Implementation Status

As of **February 27, 2026**, the project has a working config-first core pipeline and a growing verification suite.

## Delivery Progress

- **Core pipeline (CAD → mesh → solve → post):** implemented in `src/simstack/core/project.py`.
- **Semantic tag transfer + deterministic IDs:** implemented in `src/simstack/mesh/tag_transfer.py`.
- **Mesh QA checks:** coverage/overlap/quality gates implemented in `src/simstack/mesh/mesh_build.py`.
- **Physics modules:** Poisson, heat (steady/transient), elasticity, electric AC, magnetostatic, electro-thermal orchestration.
- **Caching + provenance:** run-hash output layout, provenance JSON, and stage hashes are implemented.
- **Stage-aware reuse:** cross-run CAD STEP, mesh (`mesh.msh` + `tag_map`), and solve/post output bundle reuse are implemented (with field-manifest compatibility checks).
- **ParaView helper outputs:** template + macro generation implemented in `src/simstack/io/paraview.py`.

## Supported Geometry Builders

- `block_with_hole`
- `qfn`
- `rgy0020d`
- `w61700`
- `ipmsm`

Builder registration is in `src/simstack/cad/build.py`.

## Example Config Coverage

- **Regular configs:** 8 files under `examples/configs` (including new `qfn_poisson.yaml`, `w61700_heat.yaml`, `ipmsm_magnetostatic.yaml`).
- **Sweep configs:** 2 files (`rotor_angle_sweep.yaml`, `ipmsm_angle_sweep.yaml`).
- All example configs validate through the schema loader.

## Verification Status

- Local project tests are scoped via `pytest.ini` to avoid collecting tests from vendored reference sources.
- Latest local run:
  - Command: `uv run pytest -q`
  - Result: **44 passed, 3 skipped**
  - Skips are expected for optional FEM regression tests when `dolfinx/mpi4py/petsc4py` are unavailable.

## Latest Dry-Run Artifacts (February 27, 2026)

- **QFN Poisson dry-run**
  - Command: `uv run simstack run examples/configs/qfn_poisson.yaml --dry-run`
  - Run hash/output dir: `out/0eff5f704d23c8bce56b41dc4cef92542e3989361a8a316975f7d2496c3becd5`
  - Dry-run report: `out/0eff5f704d23c8bce56b41dc4cef92542e3989361a8a316975f7d2496c3becd5/reports/dry_run.json`

- **W61700 heat dry-run**
  - Command: `uv run simstack run examples/configs/w61700_heat.yaml --dry-run`
  - Run hash/output dir: `out/df79ec94e18ffa1370d4503d7dae822e3f9b292202690edfe3217a1a973c7727`
  - Dry-run report: `out/df79ec94e18ffa1370d4503d7dae822e3f9b292202690edfe3217a1a973c7727/reports/dry_run.json`

- **IPMSM single-run dry-run**
  - Command: `uv run simstack run examples/configs/ipmsm_magnetostatic.yaml --dry-run`
  - Run hash/output dir: `out/3a80d95e23c71bea1af785fba0b9ae9bb3cd536189a1f1f2e8dc97f3698cdbc4`
  - Dry-run report: `out/3a80d95e23c71bea1af785fba0b9ae9bb3cd536189a1f1f2e8dc97f3698cdbc4/reports/dry_run.json`

- **IPMSM angle sweep dry-run**
  - Command: `uv run simstack sweep examples/configs/ipmsm_angle_sweep.yaml --dry-run`
  - Sweep root: `out/sweeps/ipmsm_angle`
  - Sweep report: `out/sweeps/ipmsm_angle/sweep_report.json`
  - Run labels/hashes:
    - `rotor_angle_deg=0deg` → `8af5b59376d6c7f5ce024b164d347aa67dda937ca51351affb6dba419a232971`
    - `rotor_angle_deg=15deg` → `cf50c24a09767e0bdb313034e9573746a8c8188dcfcb416810a7486498701bbd`
    - `rotor_angle_deg=30deg` → `8017219ee0f8edea3c036fef16523d6edee07886956091cacf40ac25fb92045a`
    - `rotor_angle_deg=45deg` → `a0caf7c6bbb990cca5c51b666cabaa91f53e2a3a060e44a7a515c55c5202a413`

## Remaining Gaps To “Goal-Ready” v1

- Full end-to-end runtime validation with `gmsh + dolfinx + petsc4py + mpi4py` in one environment is not yet part of automated gates.
- Manufactured-solution style accuracy checks are currently represented by zero-solution patch tests; richer numerical error-threshold tests can be expanded.
- `cad/tags.py` helpers are implemented, but CAD-side tag evaluation is not yet the active source for mesh tagging (mesh-side rule evaluation remains canonical).
- Dependency onboarding for the full FEM stack remains environment-specific and should be documented as a reproducible setup path.

## Suggested Next Steps

1. Add a documented full-stack environment profile and CI lane for FEM-enabled runs.
2. Add one true manufactured-solution test per primary physics module with norm/error thresholds.
3. Add an end-to-end smoke test that runs one FEM-enabled example and verifies expected artifacts.
4. Extend builder-specific examples to include part-appropriate tag/material presets.
