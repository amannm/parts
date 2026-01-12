"""Project orchestration and caching hooks (initial scaffolding)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from simstack.config import SimStackConfig, config_to_dict
from simstack.core.provenance import build_provenance
from simstack.cad.build import build_geometry
from simstack.mesh.mesh_build import GmshSession, build_gmsh_model
from simstack.mesh.import_dolfinx import model_to_mesh
from simstack.fem.solve import solve_linear_problem
from simstack.io.write import write_mesh_xdmf, write_outputs


class Project:
    def __init__(self, config: SimStackConfig, repo_root: str | Path) -> None:
        self.config = config
        self.repo_root = Path(repo_root)

    def dry_run_plan(self) -> List[str]:
        return ["cad", "mesh", "solve", "post"]

    def write_provenance(self, out_dir: str | Path) -> str:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        provenance = build_provenance(config_to_dict(self.config), self.repo_root)
        path = out_dir / "provenance.json"
        path.write_text(json.dumps(provenance, indent=2, sort_keys=True))
        return str(path)

    def write_dry_run_report(self, out_dir: str | Path) -> str:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        report: Dict[str, Any] = {
            "stages": self.dry_run_plan(),
            "note": "dry run only; no CAD/mesh/solve executed",
        }
        path = out_dir / "dry_run.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True))
        return str(path)

    def run(self) -> Dict[str, Any]:
        out_root = Path(self.config.outputs.directory)
        reports_dir = out_root / "reports"
        mesh_dir = out_root / "mesh"
        fields_dir = out_root / "fields"
        reports_dir.mkdir(parents=True, exist_ok=True)
        mesh_dir.mkdir(parents=True, exist_ok=True)
        fields_dir.mkdir(parents=True, exist_ok=True)

        from mpi4py import MPI

        comm = MPI.COMM_WORLD
        rank = comm.rank

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

        if self.config.outputs.write_mesh:
            write_mesh_xdmf(mesh, cell_tags, facet_tags, mesh_dir)
        if rank == 0:
            tag_map_path = mesh_dir / "tag_map.json"
            tag_map_path.write_text(json.dumps(tag_map, indent=2, sort_keys=True))
            if gmsh_result is not None and gmsh_result.mesh_stats:
                mesh_stats_path = mesh_dir / "mesh_stats.json"
                mesh_stats_path.write_text(json.dumps(gmsh_result.mesh_stats, indent=2, sort_keys=True))

        output_paths = write_outputs(
            mesh,
            solve_artifact.fields,
            out_dir=out_root,
            fmt=self.config.outputs.format,
        )

        provenance_path = None
        if rank == 0 and self.config.outputs.write_reports:
            provenance_path = self.write_provenance(reports_dir)
            report_path = reports_dir / "solve_report.json"
            report_path.write_text(json.dumps(solve_artifact.solver_report, indent=2, sort_keys=True))

        return {
            "outputs": output_paths,
            "provenance": provenance_path,
        }
