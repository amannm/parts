"""Project orchestration and caching hooks (initial scaffolding)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from simstack.config import SimStackConfig, config_to_dict
from simstack.core.provenance import build_provenance, stable_hash
from simstack.cad.build import build_geometry
from simstack.mesh.mesh_build import GmshSession, build_gmsh_model
from simstack.mesh.import_dolfinx import model_to_mesh
from simstack.fem.solve import solve_linear_problem
from simstack.io.write import (
    build_tag_fields,
    write_boundary_xdmf,
    write_mesh_xdmf,
    write_outputs,
    write_tag_legend,
)


class Project:
    def __init__(self, config: SimStackConfig, repo_root: str | Path) -> None:
        self.config = config
        self.repo_root = Path(repo_root)

    def run_hash(self) -> str:
        return stable_hash(config_to_dict(self.config))

    def output_root(self) -> Path:
        base = Path(self.config.outputs.directory)
        run_hash = self.run_hash()
        if base.name == run_hash:
            return base
        return base / run_hash

    def _collect_cached_outputs(self, out_root: Path) -> Dict[str, Dict[str, str]] | None:
        fields_dir = out_root / "fields"
        results: Dict[str, Dict[str, str]] = {"vtx": {}, "xdmf": {}}

        if self.config.outputs.format in {"vtx", "both"}:
            vtx_path = fields_dir / "fields.bp"
            if not vtx_path.exists():
                return None
            results["vtx"] = {"fields": str(vtx_path)}

        if self.config.outputs.format in {"xdmf", "both"}:
            xdmf_path = fields_dir / "fields.xdmf"
            if not xdmf_path.exists():
                return None
            results["xdmf"] = {"fields": str(xdmf_path)}

        return results

    def _load_cached_results(self, out_root: Path) -> Dict[str, Any] | None:
        if not out_root.exists():
            return None

        outputs = self._collect_cached_outputs(out_root)
        if outputs is None:
            return None
        tag_legend_path = out_root / "mesh" / "tag_legend.json"

        if self.config.outputs.write_mesh:
            mesh_dir = out_root / "mesh"
            mesh_path = mesh_dir / "mesh.xdmf"
            tag_map_path = mesh_dir / "tag_map.json"
            if not mesh_path.exists() or not tag_map_path.exists():
                return None
            if self.config.outputs.write_boundary_mesh:
                boundary_path = mesh_dir / "boundary.xdmf"
                if not boundary_path.exists():
                    return None

        provenance_path = out_root / "reports" / "provenance.json"
        solve_report_path = out_root / "reports" / "solve_report.json"
        if self.config.outputs.write_reports:
            if not provenance_path.exists() or not solve_report_path.exists():
                return None
            try:
                data = json.loads(provenance_path.read_text())
            except json.JSONDecodeError:
                return None
            if data.get("config_hash") != self.run_hash():
                return None

        return {
            "outputs": outputs,
            "provenance": str(provenance_path) if provenance_path.exists() else None,
            "tag_legend": str(tag_legend_path) if tag_legend_path.exists() else None,
            "run_hash": self.run_hash(),
            "out_dir": str(out_root),
            "cached": True,
        }

    def dry_run_plan(self) -> List[str]:
        return ["cad", "mesh", "solve", "post"]

    def write_provenance(
        self,
        out_dir: str | Path,
        *,
        tag_map: Dict[str, Dict[str, int]] | None = None,
        mesh_stats: Dict[str, Any] | None = None,
        tag_legend_path: str | None = None,
    ) -> str:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        provenance = build_provenance(
            config_to_dict(self.config),
            self.repo_root,
            tag_map=tag_map,
            mesh_stats=mesh_stats,
            tag_legend_path=tag_legend_path,
        )
        path = out_dir / "provenance.json"
        path.write_text(json.dumps(provenance, indent=2, sort_keys=True))
        return str(path)

    def write_dry_run_report(self, out_dir: str | Path) -> str:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        report: Dict[str, Any] = {
            "stages": self.dry_run_plan(),
            "note": "dry run only; no CAD/mesh/solve executed",
            "run_hash": self.run_hash(),
            "out_dir": str(self.output_root()),
        }
        path = out_dir / "dry_run.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True))
        return str(path)

    def _update_latest_pointer(self, out_root: Path) -> None:
        base = Path(self.config.outputs.directory)
        base.mkdir(parents=True, exist_ok=True)
        latest = base / "latest"
        if latest.exists() or latest.is_symlink():
            if latest.is_symlink() or latest.is_file():
                latest.unlink()
            else:
                return
        try:
            latest.symlink_to(out_root)
        except OSError:
            return

    def run(self) -> Dict[str, Any]:
        out_root = self.output_root()
        reports_dir = out_root / "reports"
        mesh_dir = out_root / "mesh"
        fields_dir = out_root / "fields"
        reports_dir.mkdir(parents=True, exist_ok=True)
        mesh_dir.mkdir(parents=True, exist_ok=True)
        fields_dir.mkdir(parents=True, exist_ok=True)

        from mpi4py import MPI

        comm = MPI.COMM_WORLD
        rank = comm.rank

        cached = None
        if self.config.outputs.reuse and rank == 0:
            cached = self._load_cached_results(out_root)
            if cached is not None:
                self._update_latest_pointer(out_root)
        cached = comm.bcast(cached, root=0)
        if cached is not None:
            return cached

        cad_artifact = None
        if rank == 0:
            cad_artifact = build_geometry(self.config.geometry, out_dir=out_root / "cad")
            if cad_artifact.step_path is None:
                raise RuntimeError("CAD builder did not produce a STEP path")

        gmsh_result = None
        with GmshSession():
            if rank == 0:
                gmsh_result = build_gmsh_model(
                    cad_artifact.step_path,
                    self.config.tags,
                    self.config.meshing,
                )

            mesh, cell_tags, facet_tags = model_to_mesh(
                gmsh_result.model if gmsh_result else None,
                comm,
                rank=0,
                gdim=3,
            )

        tag_map = None
        if gmsh_result is not None:
            tag_map = gmsh_result.tag_result.tag_map
        tag_map = comm.bcast(tag_map, root=0)

        solve_artifact = solve_linear_problem(
            mesh,
            cell_tags,
            facet_tags,
            self.config.physics,
            self.config.bcs,
            self.config.materials,
            self.config.solver,
            tag_map,
        )

        fields = dict(solve_artifact.fields)
        if self.config.outputs.write_tag_fields:
            fields.update(build_tag_fields(mesh, cell_tags))

        if self.config.outputs.write_mesh:
            write_mesh_xdmf(mesh, cell_tags, facet_tags, mesh_dir)
            if self.config.outputs.write_boundary_mesh:
                write_boundary_xdmf(mesh, facet_tags, mesh_dir)
        tag_legend_path = None
        if rank == 0:
            tag_map_path = mesh_dir / "tag_map.json"
            tag_map_path.write_text(json.dumps(tag_map, indent=2, sort_keys=True))
            tag_legend_path = write_tag_legend(tag_map, mesh_dir)
            if gmsh_result is not None and gmsh_result.mesh_stats:
                mesh_stats_path = mesh_dir / "mesh_stats.json"
                mesh_stats_path.write_text(json.dumps(gmsh_result.mesh_stats, indent=2, sort_keys=True))

        output_paths = write_outputs(
            mesh,
            fields,
            out_dir=out_root,
            fmt=self.config.outputs.format,
        )

        provenance_path = None
        if rank == 0 and self.config.outputs.write_reports:
            provenance_path = self.write_provenance(
                reports_dir,
                tag_map=tag_map,
                mesh_stats=gmsh_result.mesh_stats if gmsh_result is not None else None,
                tag_legend_path=tag_legend_path if rank == 0 else None,
            )
            report_path = reports_dir / "solve_report.json"
            report_path.write_text(json.dumps(solve_artifact.solver_report, indent=2, sort_keys=True))
            self._update_latest_pointer(out_root)

        return {
            "outputs": output_paths,
            "provenance": provenance_path,
            "tag_legend": str(mesh_dir / "tag_legend.json"),
            "run_hash": self.run_hash(),
            "out_dir": str(out_root),
        }
