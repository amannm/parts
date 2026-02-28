# SimStack v2

SimStack is a compact CAD-to-multiphysics pipeline with a parametric part library.

## Breaking Changes in v2

1. Tag rules are now typed (`type` + typed fields), not free-form `rule/params` objects.
2. `geometry.dimension` (`2|3`) and `geometry.coordinate_system` (`cartesian|axisymmetric`) are required runtime concepts.
3. Workflow orchestration is explicit via `workflow` (`single` or `coupled`).
4. Meshing controls are typed (`curvature_refine`, `distance_refine`, `boundary_layers`).
5. Sweep modes now include `lhs`, `sobol`, and `optuna`.
6. Unit metadata is centralized under `units` (`internal_system=SI`).

## Minimal v2 Example

```yaml
geometry:
  builder: block_with_hole
  params:
    length: 1.0
    width: 1.0
    height: 1.0
    hole_radius: 0.2
  units: m
  dimension: 3
  coordinate_system: cartesian

tags:
  facets:
    - type: PlaneAtMin
      name: left
      axis: x
    - type: PlaneAtMax
      name: right
      axis: x
  cells:
    - type: AllVolumes
      name: domain

meshing:
  global_size: 0.1

physics:
  model: heat
  parameters:
    source: 1.0
    kappa: 5.0

bcs:
  items:
    - type: dirichlet
      tag: left
      value: 300.0
    - type: robin
      tag: right
      value: 290.0
      alpha: 10.0

materials:
  by_tag:
    domain:
      kappa:
        model: polynomial
        variable: T
        reference: 293.15
        coefficients: [5.0, 0.01]

workflow:
  type: single

units:
  internal_system: SI

outputs:
  directory: out
  format: vtx
```

## Parts Catalog CLI

- `simstack parts list`
- `simstack parts show <name>`
- `simstack parts scaffold-config <name> --out <path>`

## Sweep / Optimization CLI

- `simstack sweep run <config>`
- `simstack sweep optimize <config>`
