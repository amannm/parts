"""DOLFINx mesh import helpers (stub)."""

from __future__ import annotations

from typing import Any


def model_to_mesh(model: Any, comm: Any, rank: int, gdim: int) -> Any:
    """Convert a Gmsh model to a distributed DOLFINx mesh (stub)."""
    raise NotImplementedError("DOLFINx import is not implemented yet.")


def read_from_msh(path: str, comm: Any) -> Any:
    """Read a .msh file into DOLFINx (stub)."""
    raise NotImplementedError("DOLFINx import is not implemented yet.")
