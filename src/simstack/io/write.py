"""Output writers for mesh and fields."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def _write_vtx(mesh: Any, fields: Dict[str, Any], out_dir: Path) -> Dict[str, str]:
    from dolfinx.io import VTXWriter

    out_dir.mkdir(parents=True, exist_ok=True)
    for name, field in fields.items():
        field.name = name

    path = out_dir / "fields.bp"
    with VTXWriter(mesh.comm, str(path), list(fields.values())) as vtx:
        vtx.write(0.0)
    return {"fields": str(path)}


def _write_xdmf(mesh: Any, fields: Dict[str, Any], out_dir: Path) -> Dict[str, str]:
    from dolfinx.io import XDMFFile

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "fields.xdmf"
    with XDMFFile(mesh.comm, str(path), "w") as xdmf:
        xdmf.write_mesh(mesh)
        for field in fields.values():
            xdmf.write_function(field)
    return {"fields": str(path)}


def write_mesh_xdmf(mesh: Any, cell_tags: Any, facet_tags: Any, out_dir: Path) -> str:
    from dolfinx.io import XDMFFile

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "mesh.xdmf"
    with XDMFFile(mesh.comm, str(path), "w") as xdmf:
        xdmf.write_mesh(mesh)
        if cell_tags is not None:
            try:
                xdmf.write_meshtags(cell_tags)
            except AttributeError:
                pass
        if facet_tags is not None:
            try:
                xdmf.write_meshtags(facet_tags)
            except AttributeError:
                pass
    return str(path)


def write_outputs(
    mesh: Any,
    fields: Dict[str, Any],
    out_dir: str | Path,
    fmt: str = "vtx",
) -> Dict[str, Dict[str, str]]:
    out_dir = Path(out_dir)
    results: Dict[str, Dict[str, str]] = {"vtx": {}, "xdmf": {}}

    if fmt in {"vtx", "both"}:
        results["vtx"] = _write_vtx(mesh, fields, out_dir / "fields")
    if fmt in {"xdmf", "both"}:
        results["xdmf"] = _write_xdmf(mesh, fields, out_dir / "fields")

    return results
