"""Mesh node adapter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from simstack.mesh.import_dolfinx import model_to_mesh, read_from_msh
from simstack.mesh.mesh_build import GmshSession, build_gmsh_model


def _write_gmsh_msh(out_root: Path) -> str:
    import gmsh

    mesh_dir = out_root / "mesh"
    mesh_dir.mkdir(parents=True, exist_ok=True)
    mesh_msh_path = mesh_dir / "mesh.msh"
    gmsh.write(str(mesh_msh_path))
    return str(mesh_msh_path)


def run_mesh(ctx: Any) -> Dict[str, Any]:
    step_path = ctx.state.get("cad_step_path")
    if not step_path:
        raise RuntimeError("Missing cad_step_path in state")

    geometry_dim = int(ctx.config.geometry.dimension)

    mesh_msh_path = None
    tag_map = None
    mesh_stats = None
    gmsh_model = None

    with GmshSession():
        if ctx.rank == 0:
            gmsh_result = build_gmsh_model(
                step_path,
                ctx.config.tagging,
                ctx.config.mesh,
                geometry_dim=geometry_dim,
            )
            gmsh_model = gmsh_result.model
            tag_map = gmsh_result.tag_result.tag_map
            mesh_stats = gmsh_result.mesh_stats if gmsh_result.mesh_stats else {}
            mesh_msh_path = _write_gmsh_msh(Path(ctx.out_root))

        mesh, cell_tags, facet_tags = model_to_mesh(
            gmsh_model if ctx.rank == 0 else None,
            ctx.comm,
            rank=0,
            gdim=geometry_dim,
        )

    mesh_msh_path = ctx.comm.bcast(mesh_msh_path, root=0)
    tag_map = ctx.comm.bcast(tag_map, root=0)
    mesh_stats = ctx.comm.bcast(mesh_stats, root=0)

    if tag_map is None:
        tag_map = {}

    state_updates = {
        "mesh": mesh,
        "cell_tags": cell_tags,
        "facet_tags": facet_tags,
        "tag_map": tag_map,
        "mesh_stats": mesh_stats,
        "mesh_msh_path": mesh_msh_path,
        "geometry_dim": geometry_dim,
    }

    outputs = {
        "mesh_msh": mesh_msh_path,
        "cell_tag_count": len(tag_map.get("cells", {})) if isinstance(tag_map, dict) else 0,
        "facet_tag_count": len(tag_map.get("facets", {})) if isinstance(tag_map, dict) else 0,
        "geometry_dim": geometry_dim,
    }

    cache_payload = {
        "mesh_msh_path": mesh_msh_path,
        "tag_map": tag_map,
        "mesh_stats": mesh_stats,
        "geometry_dim": geometry_dim,
    }

    return {
        "state_updates": state_updates,
        "cache_payload": cache_payload,
        "outputs": outputs,
    }


def _try_load_tag_map(mesh_msh_path: str | None, fallback: Dict[str, Any]) -> Dict[str, Any]:
    if not mesh_msh_path:
        return fallback
    mesh_dir = Path(mesh_msh_path).parent
    tag_map_file = mesh_dir / "tag_map.json"
    if not tag_map_file.exists():
        return fallback
    try:
        raw = json.loads(tag_map_file.read_text())
    except json.JSONDecodeError:
        return fallback
    return raw if isinstance(raw, dict) else fallback


def hydrate_mesh(ctx: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    mesh_msh_path = payload.get("mesh_msh_path")
    if not mesh_msh_path:
        raise RuntimeError("mesh cache payload is missing mesh_msh_path")

    mesh, cell_tags, facet_tags = read_from_msh(str(mesh_msh_path), ctx.comm)
    tag_map = payload.get("tag_map", {})
    if not tag_map:
        tag_map = _try_load_tag_map(str(mesh_msh_path), {})

    return {
        "mesh": mesh,
        "cell_tags": cell_tags,
        "facet_tags": facet_tags,
        "tag_map": tag_map,
        "mesh_stats": payload.get("mesh_stats", {}),
        "mesh_msh_path": mesh_msh_path,
        "geometry_dim": payload.get("geometry_dim"),
    }
