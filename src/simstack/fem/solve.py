"""Solver orchestration."""

from __future__ import annotations

from typing import Any, Dict

from simstack.config import BCsConfig, PhysicsConfig, SolverConfig
from simstack.core.registry import DEFAULT_REGISTRY
from simstack.core.artifacts import SolveArtifact


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

    coeffs = model.build_coefficients(mesh, cell_tags, None, physics.parameters)
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
    return SolveArtifact(fields=fields, derived_fields={}, solver_report=solver_info, timings={})
