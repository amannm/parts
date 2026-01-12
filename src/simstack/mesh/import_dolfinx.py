"""DOLFINx mesh import helpers."""

from __future__ import annotations

from typing import Any


def model_to_mesh(model: Any, comm: Any, rank: int, gdim: int):
    from dolfinx.io import gmshio

    return gmshio.model_to_mesh(model, comm, rank, gdim=gdim)


def read_from_msh(path: str, comm: Any):
    from dolfinx.io import gmshio

    return gmshio.read_from_msh(path, comm)
