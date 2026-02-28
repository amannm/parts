"""Post-processing node adapter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from simstack.io.paraview import write_paraview_template
from simstack.io.write import write_boundary_xdmf, write_mesh_xdmf, write_tag_legend


def run_post(ctx: Any) -> Dict[str, Any]:
    mesh = ctx.state.get("mesh")
    cell_tags = ctx.state.get("cell_tags")
    facet_tags = ctx.state.get("facet_tags")
    tag_map = ctx.state.get("tag_map")
    output_paths = ctx.state.get("output_paths")

    if mesh is None or cell_tags is None or facet_tags is None or tag_map is None or output_paths is None:
        raise RuntimeError("Missing state required for post-processing")

    mesh_dir = Path(ctx.out_root) / "mesh"
    mesh_dir.mkdir(parents=True, exist_ok=True)

    mesh_xdmf_path = None
    boundary_xdmf_path = None
    if ctx.config.outputs.write_mesh:
        mesh_xdmf_path = write_mesh_xdmf(mesh, cell_tags, facet_tags, mesh_dir)
        if ctx.config.outputs.write_boundary_mesh:
            boundary_xdmf_path = write_boundary_xdmf(mesh, facet_tags, mesh_dir)

    tag_map_path = None
    tag_legend_path = None
    mesh_stats_path = None
    tag_debug_report_path = None

    if ctx.rank == 0:
        tag_map_file = mesh_dir / "tag_map.json"
        tag_map_file.write_text(json.dumps(tag_map, indent=2, sort_keys=True))
        tag_map_path = str(tag_map_file)
        tag_legend_path = write_tag_legend(tag_map, mesh_dir)

        mesh_stats = ctx.state.get("mesh_stats")
        if isinstance(mesh_stats, dict) and mesh_stats:
            stats_file = mesh_dir / "mesh_stats.json"
            stats_file.write_text(json.dumps(mesh_stats, indent=2, sort_keys=True))
            mesh_stats_path = str(stats_file)

            tag_debug = mesh_stats.get("tag_debug")
            if isinstance(tag_debug, dict):
                debug_file = mesh_dir / "tag_debug_report.json"
                debug_file.write_text(json.dumps(tag_debug, indent=2, sort_keys=True))
                tag_debug_report_path = str(debug_file)

    tag_map_path = ctx.comm.bcast(tag_map_path, root=0)
    tag_legend_path = ctx.comm.bcast(tag_legend_path, root=0)
    mesh_stats_path = ctx.comm.bcast(mesh_stats_path, root=0)
    tag_debug_report_path = ctx.comm.bcast(tag_debug_report_path, root=0)

    paraview_state_path = None
    paraview_macro_path = None
    if ctx.rank == 0 and ctx.config.outputs.write_paraview_state:
        paraview_bundle = write_paraview_template(
            ctx.out_root,
            output_paths,
            mesh_path=mesh_xdmf_path,
            boundary_path=boundary_xdmf_path,
            tag_map_path=tag_map_path,
            provenance_path=None,
            state_name=ctx.config.outputs.paraview_state_name,
        )
        if paraview_bundle is not None:
            paraview_state_path = paraview_bundle.get("state")
            paraview_macro_path = paraview_bundle.get("macro")

    paraview_state_path = ctx.comm.bcast(paraview_state_path, root=0)
    paraview_macro_path = ctx.comm.bcast(paraview_macro_path, root=0)

    state_updates = {
        "mesh_xdmf_path": mesh_xdmf_path,
        "boundary_xdmf_path": boundary_xdmf_path,
        "tag_map_path": tag_map_path,
        "tag_legend_path": tag_legend_path,
        "mesh_stats_path": mesh_stats_path,
        "tag_debug_report_path": tag_debug_report_path,
        "paraview_state_path": paraview_state_path,
        "paraview_macro_path": paraview_macro_path,
    }

    outputs = {
        "mesh_xdmf": mesh_xdmf_path,
        "boundary_xdmf": boundary_xdmf_path,
        "tag_map": tag_map_path,
        "tag_legend": tag_legend_path,
        "mesh_stats": mesh_stats_path,
        "tag_debug_report": tag_debug_report_path,
        "paraview_state": paraview_state_path,
    }

    return {
        "state_updates": state_updates,
        "cache_payload": state_updates,
        "outputs": outputs,
    }


def hydrate_post(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "mesh_xdmf_path": payload.get("mesh_xdmf_path"),
        "boundary_xdmf_path": payload.get("boundary_xdmf_path"),
        "tag_map_path": payload.get("tag_map_path"),
        "tag_legend_path": payload.get("tag_legend_path"),
        "mesh_stats_path": payload.get("mesh_stats_path"),
        "tag_debug_report_path": payload.get("tag_debug_report_path"),
        "paraview_state_path": payload.get("paraview_state_path"),
        "paraview_macro_path": payload.get("paraview_macro_path"),
    }
