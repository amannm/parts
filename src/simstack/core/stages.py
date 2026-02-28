"""Concrete pipeline stages for the default SimStack workflow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from simstack.cad.build import build_geometry
from simstack.config import config_to_dict
from simstack.core.pipeline import RunContext, Stage
from simstack.io.paraview import write_paraview_template
from simstack.io.write import (
    build_tag_fields,
    write_boundary_xdmf,
    write_mesh_xdmf,
    write_outputs,
    write_tag_legend,
)
from simstack.mesh.import_dolfinx import model_to_mesh
from simstack.mesh.mesh_build import GmshSession, build_gmsh_model
from simstack.workflow.engine import run_workflow


def _write_gmsh_msh(out_root: Path) -> str:
    import gmsh

    mesh_dir = out_root / "mesh"
    mesh_dir.mkdir(parents=True, exist_ok=True)
    mesh_msh_path = mesh_dir / "mesh.msh"
    gmsh.write(str(mesh_msh_path))
    return str(mesh_msh_path)


class CadStage(Stage):
    name = "cad"
    deps = ()

    def fingerprint_payload(self, ctx: RunContext) -> Dict[str, Any]:
        cfg = config_to_dict(ctx.config)
        return {"geometry": cfg.get("geometry", {})}

    def run(self, ctx: RunContext) -> None:
        step_path = None
        cad_provenance: Dict[str, Any] | None = None
        if ctx.rank == 0:
            artifact = build_geometry(ctx.config.geometry, out_dir=ctx.out_root / "cad")
            step_path = artifact.step_path
            cad_provenance = artifact.cad_provenance
            if step_path is None:
                raise RuntimeError("CAD builder did not produce a STEP path")

        step_path = ctx.comm.bcast(step_path, root=0)
        cad_provenance = ctx.comm.bcast(cad_provenance, root=0)

        ctx.set("cad_step_path", step_path)
        ctx.set("cad_provenance", cad_provenance or {})

    def outputs(self, ctx: RunContext) -> Dict[str, Any]:
        return {"step": ctx.get("cad_step_path")}


class MeshStage(Stage):
    name = "mesh"
    deps = ("cad",)

    def fingerprint_payload(self, ctx: RunContext) -> Dict[str, Any]:
        cfg = config_to_dict(ctx.config)
        return {
            "geometry": cfg.get("geometry", {}),
            "tags": cfg.get("tags", {}),
            "meshing": cfg.get("meshing", {}),
        }

    def run(self, ctx: RunContext) -> None:
        step_path = ctx.require("cad_step_path")
        geometry_dim = int(ctx.config.geometry.dimension)

        mesh_msh_path = None
        tag_map = None
        mesh_stats = None
        gmsh_model = None

        with GmshSession():
            if ctx.rank == 0:
                gmsh_result = build_gmsh_model(
                    step_path,
                    ctx.config.tags,
                    ctx.config.meshing,
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

        ctx.set("mesh", mesh)
        ctx.set("cell_tags", cell_tags)
        ctx.set("facet_tags", facet_tags)
        ctx.set("tag_map", tag_map)
        ctx.set("mesh_stats", mesh_stats)
        ctx.set("mesh_msh_path", mesh_msh_path)
        ctx.set("geometry_dim", geometry_dim)

    def outputs(self, ctx: RunContext) -> Dict[str, Any]:
        tag_map = ctx.get("tag_map", {})
        cell_count = len(tag_map.get("cells", {})) if isinstance(tag_map, dict) else 0
        facet_count = len(tag_map.get("facets", {})) if isinstance(tag_map, dict) else 0
        return {
            "mesh_msh": ctx.get("mesh_msh_path"),
            "cell_tag_count": cell_count,
            "facet_tag_count": facet_count,
            "geometry_dim": ctx.get("geometry_dim"),
        }


class SolveStage(Stage):
    name = "solve"
    deps = ("mesh",)

    def fingerprint_payload(self, ctx: RunContext) -> Dict[str, Any]:
        cfg = config_to_dict(ctx.config)
        return {
            "meshing": cfg.get("meshing", {}),
            "physics": cfg.get("physics", {}),
            "materials": cfg.get("materials", {}),
            "bcs": cfg.get("bcs", {}),
            "solver": cfg.get("solver", {}),
            "workflow": cfg.get("workflow", {}),
            "units": cfg.get("units", {}),
            "outputs": {
                "format": cfg.get("outputs", {}).get("format"),
                "write_tag_fields": cfg.get("outputs", {}).get("write_tag_fields"),
            },
        }

    def run(self, ctx: RunContext) -> None:
        mesh = ctx.require("mesh")
        cell_tags = ctx.require("cell_tags")
        facet_tags = ctx.require("facet_tags")
        tag_map = ctx.require("tag_map")

        solve_artifact = run_workflow(
            mesh,
            cell_tags,
            facet_tags,
            ctx.config,
            tag_map,
        )

        fields = dict(solve_artifact.fields)
        if ctx.config.outputs.write_tag_fields:
            fields.update(build_tag_fields(mesh, cell_tags))

        output_paths = write_outputs(
            mesh,
            fields,
            out_dir=ctx.out_root,
            fmt=ctx.config.outputs.format,
        )
        field_names = sorted(fields.keys())

        solve_report_path = None
        if ctx.rank == 0 and ctx.config.outputs.write_reports:
            report_dir = Path(ctx.out_root) / "reports"
            report_dir.mkdir(parents=True, exist_ok=True)
            report_path = report_dir / "solve_report.json"
            report_path.write_text(json.dumps(solve_artifact.solver_report, indent=2, sort_keys=True))
            solve_report_path = str(report_path)

        solve_report_path = ctx.comm.bcast(solve_report_path, root=0)

        ctx.set("output_paths", output_paths)
        ctx.set("field_names", field_names)
        ctx.set("solve_report_path", solve_report_path)

    def outputs(self, ctx: RunContext) -> Dict[str, Any]:
        return {
            "formats": [fmt for fmt, data in ctx.get("output_paths", {}).items() if data],
            "field_count": len(ctx.get("field_names", [])),
            "solve_report": ctx.get("solve_report_path"),
        }


class PostStage(Stage):
    name = "post"
    deps = ("solve",)

    def fingerprint_payload(self, ctx: RunContext) -> Dict[str, Any]:
        cfg = config_to_dict(ctx.config)
        return {"outputs": cfg.get("outputs", {})}

    def run(self, ctx: RunContext) -> None:
        mesh = ctx.require("mesh")
        cell_tags = ctx.require("cell_tags")
        facet_tags = ctx.require("facet_tags")
        tag_map = ctx.require("tag_map")
        output_paths = ctx.require("output_paths")

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

            mesh_stats = ctx.get("mesh_stats")
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

        ctx.set("mesh_xdmf_path", mesh_xdmf_path)
        ctx.set("boundary_xdmf_path", boundary_xdmf_path)
        ctx.set("tag_map_path", tag_map_path)
        ctx.set("tag_legend_path", tag_legend_path)
        ctx.set("mesh_stats_path", mesh_stats_path)
        ctx.set("tag_debug_report_path", tag_debug_report_path)
        ctx.set("paraview_state_path", paraview_state_path)
        ctx.set("paraview_macro_path", paraview_macro_path)

    def outputs(self, ctx: RunContext) -> Dict[str, Any]:
        return {
            "mesh_xdmf": ctx.get("mesh_xdmf_path"),
            "boundary_xdmf": ctx.get("boundary_xdmf_path"),
            "tag_map": ctx.get("tag_map_path"),
            "tag_legend": ctx.get("tag_legend_path"),
            "mesh_stats": ctx.get("mesh_stats_path"),
            "tag_debug_report": ctx.get("tag_debug_report_path"),
            "paraview_state": ctx.get("paraview_state_path"),
        }
