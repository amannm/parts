"""Output writers for mesh and fields."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


def build_tag_fields(mesh: Any, cell_tags: Any) -> Dict[str, Any]:
    if cell_tags is None:
        return {}

    from simstack.fem.coeffs import build_dg0_field

    tag_ids = {int(tag_id) for tag_id in cell_tags.values}
    by_id = {tag_id: {"tag_id": float(tag_id)} for tag_id in tag_ids}
    field = build_dg0_field(mesh, cell_tags, by_id, "tag_id", 0.0)
    field.name = "cell_tag"
    return {"cell_tag": field}


def write_tag_legend(tag_map: Dict[str, Dict[str, int]], out_dir: Path) -> str:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "tag_legend.json"
    path.write_text(json.dumps(tag_map, indent=2, sort_keys=True))
    return str(path)


def write_boundary_xdmf(mesh: Any, facet_tags: Any, out_dir: Path) -> str | None:
    if facet_tags is None:
        return None

    import numpy as np
    from dolfinx import mesh as dmesh
    from dolfinx.io import XDMFFile
    from simstack.fem.coeffs import build_dg0_field

    fdim = mesh.topology.dim - 1
    facets = dmesh.exterior_facet_indices(mesh.topology)
    if facets.size == 0:
        return None
    facets = np.unique(np.asarray(facets, dtype=np.int32))

    submesh, entity_map, _, _ = dmesh.create_submesh(mesh, fdim, facets)
    num_local = submesh.topology.index_map(submesh.topology.dim).size_local
    sub_entities = np.arange(num_local, dtype=np.int32)
    parent_facets = entity_map.sub_topology_to_topology(sub_entities, False)

    parent_values = {int(idx): int(val) for idx, val in zip(facet_tags.indices, facet_tags.values)}
    values = np.asarray([parent_values.get(int(p), 0) for p in parent_facets], dtype=np.int32)
    sub_tags = dmesh.meshtags(submesh, submesh.topology.dim, sub_entities, values)

    tag_ids = {int(v) for v in values if int(v) != 0}
    by_id = {tag_id: {"tag_id": float(tag_id)} for tag_id in tag_ids}
    tag_field = build_dg0_field(submesh, sub_tags, by_id, "tag_id", 0.0)
    tag_field.name = "facet_tag"

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "boundary.xdmf"
    with XDMFFile(submesh.comm, str(path), "w") as xdmf:
        xdmf.write_mesh(submesh)
        try:
            xdmf.write_meshtags(sub_tags)
        except AttributeError:
            pass
        xdmf.write_function(tag_field)
    return str(path)


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
