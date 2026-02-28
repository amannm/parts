from __future__ import annotations

from typing import Any, Dict, Tuple

import numpy as np
import pytest

from simstack.config import BCsConfig, MaterialsConfig, PhysicsConfig, SolverConfig
from simstack.fem.solve import solve_problem


def _require_fem_stack() -> None:
    pytest.importorskip("dolfinx")
    pytest.importorskip("mpi4py")
    pytest.importorskip("petsc4py")


def _build_mesh_with_tags() -> Tuple[Any, Any, Any, Dict[str, Dict[str, int]]]:
    from mpi4py import MPI
    from dolfinx import mesh as dmesh

    mesh = dmesh.create_unit_cube(MPI.COMM_WORLD, 3, 3, 3)
    tdim = mesh.topology.dim
    fdim = tdim - 1

    mesh.topology.create_connectivity(fdim, tdim)

    cell_map = mesh.topology.index_map(tdim)
    num_cells = cell_map.size_local + cell_map.num_ghosts
    cell_indices = np.arange(num_cells, dtype=np.int32)
    cell_values = np.full(num_cells, 21, dtype=np.int32)
    cell_tags = dmesh.meshtags(mesh, tdim, cell_indices, cell_values)

    boundary_facets = dmesh.exterior_facet_indices(mesh.topology)
    boundary_facets = np.asarray(boundary_facets, dtype=np.int32)
    facet_values = np.full(boundary_facets.size, 11, dtype=np.int32)
    facet_tags = dmesh.meshtags(mesh, fdim, boundary_facets, facet_values)

    tag_map = {"facets": {"boundary": 11}, "cells": {"domain": 21}}
    return mesh, cell_tags, facet_tags, tag_map


def _zero_bcs() -> BCsConfig:
    return BCsConfig.model_validate(
        {
            "items": [
                {
                    "type": "dirichlet",
                    "tag": "boundary",
                    "value": 0.0,
                }
            ]
        }
    )


def _zero_vector_bcs() -> BCsConfig:
    return BCsConfig.model_validate(
        {
            "items": [
                {
                    "type": "dirichlet",
                    "tag": "boundary",
                    "value": [0.0, 0.0, 0.0],
                }
            ]
        }
    )


def test_poisson_zero_solution_patch() -> None:
    _require_fem_stack()
    mesh, cell_tags, facet_tags, tag_map = _build_mesh_with_tags()

    physics = PhysicsConfig(model="poisson", parameters={"kappa": 1.0, "source": 0.0})
    materials = MaterialsConfig.model_validate({"by_tag": {"domain": {"kappa": 1.0}}})
    bcs = _zero_bcs()
    solver = SolverConfig.model_validate({"preset": "linear_default", "options": {}})

    artifact = solve_problem(mesh, cell_tags, facet_tags, physics, bcs, materials, solver, tag_map)
    field = artifact.fields["u"]
    max_abs = float(np.max(np.abs(field.x.array)))

    assert max_abs < 1e-10
    assert int(artifact.solver_report["iterations"]) >= 0


def test_heat_zero_solution_patch() -> None:
    _require_fem_stack()
    mesh, cell_tags, facet_tags, tag_map = _build_mesh_with_tags()

    physics = PhysicsConfig(model="heat", parameters={"kappa": 2.0, "source": 0.0})
    materials = MaterialsConfig.model_validate({"by_tag": {"domain": {"kappa": 2.0}}})
    bcs = _zero_bcs()
    solver = SolverConfig.model_validate({"preset": "linear_default", "options": {}})

    artifact = solve_problem(mesh, cell_tags, facet_tags, physics, bcs, materials, solver, tag_map)
    field = artifact.fields["T"]
    max_abs = float(np.max(np.abs(field.x.array)))

    assert max_abs < 1e-10
    assert int(artifact.solver_report["iterations"]) >= 0


def test_elasticity_zero_displacement_patch() -> None:
    _require_fem_stack()
    mesh, cell_tags, facet_tags, tag_map = _build_mesh_with_tags()

    physics = PhysicsConfig(
        model="elasticity",
        parameters={
            "E": 100e9,
            "nu": 0.3,
            "body_force": [0.0, 0.0, 0.0],
        },
    )
    materials = MaterialsConfig.model_validate({"by_tag": {"domain": {"E": 100e9, "nu": 0.3}}})
    bcs = _zero_vector_bcs()
    solver = SolverConfig.model_validate({"preset": "linear_default", "options": {}})

    artifact = solve_problem(mesh, cell_tags, facet_tags, physics, bcs, materials, solver, tag_map)
    field = artifact.fields["u"]
    max_abs = float(np.max(np.abs(field.x.array)))

    assert max_abs < 1e-10
    assert int(artifact.solver_report["iterations"]) >= 0
