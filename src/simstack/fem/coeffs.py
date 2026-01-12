"""Coefficient field helpers."""

from __future__ import annotations

from typing import Any, Dict

from petsc4py import PETSc


def build_dg0_field(
    mesh: Any,
    cell_tags: Any,
    by_id: Dict[int, Dict[str, Any]],
    prop: str,
    default: float,
):
    from dolfinx import fem

    V0 = fem.FunctionSpace(mesh, ("DG", 0))
    field = fem.Function(V0)
    field.x.array[:] = PETSc.ScalarType(default)

    if cell_tags is None or not by_id:
        field.x.scatter_forward()
        return field

    for tag_id, props in by_id.items():
        if prop not in props:
            continue
        value = PETSc.ScalarType(props[prop])
        cells = cell_tags.find(tag_id)
        if len(cells) == 0:
            continue
        dofs = fem.locate_dofs_topological(V0, mesh.topology.dim, cells)
        field.x.array[dofs] = value

    field.x.scatter_forward()
    return field
