"""Solver orchestration."""

from __future__ import annotations

from typing import Any, Dict

from simstack.config import BCsConfig, MaterialsConfig, PhysicsConfig, SolverConfig
from simstack.core.registry import DEFAULT_REGISTRY
from simstack.core.artifacts import SolveArtifact
from simstack.fem.materials import build_matdb


def _merge_solver_options(solver: SolverConfig) -> Dict[str, Any]:
    options: Dict[str, Any] = {}
    preset = DEFAULT_REGISTRY.solver_presets.get(solver.preset, {})
    options.update(preset)
    options.update(solver.options)
    return options


def solve_linear_problem(
    mesh: Any,
    cell_tags: Any,
    facet_tags: Any,
    physics: PhysicsConfig,
    bcs: BCsConfig,
    materials: MaterialsConfig,
    solver: SolverConfig,
    tag_map: Dict[str, Dict[str, int]],
) -> SolveArtifact:
    from dolfinx import fem
    from dolfinx.fem import petsc
    from ufl import Measure

    model_factory = DEFAULT_REGISTRY.get_physics(physics.model)
    model = model_factory()

    field_spec = model.declare_fields(physics.parameters)
    spaces = model.build_spaces(mesh, field_spec, physics.parameters)

    matdb = build_matdb(materials, tag_map)
    coeffs = model.build_coefficients(mesh, cell_tags, matdb, physics.parameters)
    measures = {
        "dx": Measure("dx", domain=mesh, subdomain_data=cell_tags),
        "ds": Measure("ds", domain=mesh, subdomain_data=facet_tags),
    }

    bc_payload = {
        "bcs": [bc.model_dump(mode="json") for bc in bcs.items],
        "tag_map": tag_map,
    }
    dirichlet_bcs, natural_terms = model.build_bcs(spaces["V"], facet_tags, bc_payload)

    a, L = model.build_forms(spaces, coeffs, measures, physics.parameters)
    if natural_terms:
        for term in natural_terms:
            L += term

    options = _merge_solver_options(solver)
    problem = petsc.LinearProblem(a, L, bcs=dirichlet_bcs, petsc_options=options)
    uh = problem.solve()

    solver_info = {
        "converged_reason": problem.solver.getConvergedReason(),
        "iterations": problem.solver.getIterationNumber(),
    }

    fields = {"u": uh}
    for derived in model.outputs(fields, coeffs, physics.parameters):
        name = derived.get("name")
        field = derived.get("field")
        if name and field is not None:
            fields[name] = field
    return SolveArtifact(fields=fields, derived_fields={}, solver_report=solver_info, timings={})
