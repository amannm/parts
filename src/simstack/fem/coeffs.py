"""Coefficient field helpers."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Sequence

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


def _coerce_vector(value: Any, gdim: int, name: str) -> list[float]:
    if value is None:
        return [0.0] * gdim
    if isinstance(value, (int, float)):
        return [float(value)] * gdim
    if isinstance(value, (list, tuple)):
        if len(value) != gdim:
            raise ValueError(f"{name} must have length {gdim}")
        return [float(v) for v in value]
    if isinstance(value, Iterable):
        values = list(value)
        if len(values) != gdim:
            raise ValueError(f"{name} must have length {gdim}")
        return [float(v) for v in values]
    raise TypeError(f"{name} must be a number or sequence of length {gdim}")


def build_dg0_vector_field(
    mesh: Any,
    cell_tags: Any,
    by_id: Dict[int, Dict[str, Any]],
    prop: str,
    default: Sequence[float] | float,
):
    from dolfinx import fem
    import numpy as np

    gdim = mesh.geometry.dim
    default_vec = _coerce_vector(default, gdim, prop)
    V0 = fem.VectorFunctionSpace(mesh, ("DG", 0))
    field = fem.Function(V0)

    default_arr = np.array(default_vec, dtype=PETSc.ScalarType)
    num_cells = mesh.topology.index_map(mesh.topology.dim).size_local
    for cell in range(num_cells):
        dofs = V0.dofmap.cell_dofs(cell)
        field.x.array[dofs] = default_arr

    if cell_tags is None or not by_id:
        field.x.scatter_forward()
        return field

    for tag_id, props in by_id.items():
        if prop not in props:
            continue
        value = _coerce_vector(props[prop], gdim, prop)
        cells = cell_tags.find(tag_id)
        if len(cells) == 0:
            continue
        for cell in cells:
            dofs = V0.dofmap.cell_dofs(int(cell))
            field.x.array[dofs] = np.array(value, dtype=PETSc.ScalarType)

    field.x.scatter_forward()
    return field
