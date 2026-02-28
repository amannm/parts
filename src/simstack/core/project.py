"""Project orchestration built around explicit pipeline stages."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any, Dict, List

from simstack.config import SimStackConfig, config_to_dict
from simstack.core.pipeline import RunContext, StagePipeline
from simstack.core.provenance import build_provenance, build_stage_hashes, stable_hash
from simstack.core.stages import CadStage, MeshStage, PostStage, SolveStage


class Project:
    def __init__(self, config: SimStackConfig, repo_root: str | Path) -> None:
        self.config = config
        self.repo_root = Path(repo_root)

    def run_hash(self) -> str:
        return stable_hash(config_to_dict(self.config))

    def stage_hashes(self) -> Dict[str, str]:
        return build_stage_hashes(config_to_dict(self.config))

    def output_root(self) -> Path:
        base = Path(self.config.outputs.directory)
        run_hash = self.run_hash()
        if base.name == run_hash:
            return base
        return base / run_hash

    def dry_run_plan(self) -> List[str]:
        pipeline = StagePipeline([CadStage(), MeshStage(), SolveStage(), PostStage()])
        return pipeline.stage_names()

    def write_provenance(
        self,
        out_dir: str | Path,
        *,
        tag_map: Dict[str, Dict[str, int]] | None = None,
        mesh_stats: Dict[str, Any] | None = None,
        tag_legend_path: str | None = None,
        stage_hashes: Dict[str, str] | None = None,
    ) -> str:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        provenance = build_provenance(
            config_to_dict(self.config),
            self.repo_root,
            tag_map=tag_map,
            mesh_stats=mesh_stats,
            tag_legend_path=tag_legend_path,
            stage_hashes=stage_hashes,
        )
        path = out_dir / "provenance.json"
        path.write_text(json.dumps(provenance, indent=2, sort_keys=True))
        return str(path)

    def write_dry_run_report(self, out_dir: str | Path) -> str:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        report: Dict[str, Any] = {
            "stages": self.dry_run_plan(),
            "stage_hashes": self.stage_hashes(),
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

    def _write_artifact_index(
        self,
        out_root: Path,
        *,
        stage_hashes: Dict[str, str],
        stage_records: List[Dict[str, Any]],
        output_paths: Dict[str, Dict[str, str]],
        field_names: List[str] | None,
        cad_step_path: str | None,
        mesh_msh_path: str | None,
        mesh_xdmf_path: str | None,
        boundary_xdmf_path: str | None,
        tag_map_path: str | None,
        tag_legend_path: str | None,
        mesh_stats_path: str | None,
        provenance_path: str | None,
        solve_report_path: str | None,
        paraview_state_path: str | None,
        paraview_macro_path: str | None,
    ) -> str:
        reports_dir = out_root / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        index_payload = {
            "run_hash": self.run_hash(),
            "stage_hashes": stage_hashes,
            "stages": stage_records,
            "artifacts": {
                "cad": {
                    "step": cad_step_path,
                },
                "mesh": {
                    "mesh_msh": mesh_msh_path,
                    "mesh_xdmf": mesh_xdmf_path,
                    "boundary_xdmf": boundary_xdmf_path,
                    "tag_map": tag_map_path,
                    "tag_legend": tag_legend_path,
                    "mesh_stats": mesh_stats_path,
                },
                "fields": {**output_paths, "names": field_names or []},
                "reports": {
                    "provenance": provenance_path,
                    "solve_report": solve_report_path,
                },
                "paraview": {
                    "state": paraview_state_path,
                    "macro": paraview_macro_path,
                },
            },
        }

        path = reports_dir / "artifact_index.json"
        path.write_text(json.dumps(index_payload, indent=2, sort_keys=True))
        return str(path)

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

        ctx = RunContext(
            config=self.config,
            repo_root=self.repo_root,
            out_root=out_root,
            comm=comm,
            rank=rank,
        )

        pipeline = StagePipeline([CadStage(), MeshStage(), SolveStage(), PostStage()])
        records = pipeline.run(ctx)

        result: Dict[str, Any] | None = None
        if rank == 0:
            stage_hashes = self.stage_hashes()
            stage_records = [dataclasses.asdict(record) for record in records]

            provenance_path = None
            if self.config.outputs.write_reports:
                provenance_path = self.write_provenance(
                    reports_dir,
                    tag_map=ctx.get("tag_map"),
                    mesh_stats=ctx.get("mesh_stats"),
                    tag_legend_path=ctx.get("tag_legend_path"),
                    stage_hashes=stage_hashes,
                )

            artifact_index_path = self._write_artifact_index(
                out_root,
                stage_hashes=stage_hashes,
                stage_records=stage_records,
                output_paths=ctx.get("output_paths", {}),
                field_names=ctx.get("field_names"),
                cad_step_path=ctx.get("cad_step_path"),
                mesh_msh_path=ctx.get("mesh_msh_path"),
                mesh_xdmf_path=ctx.get("mesh_xdmf_path"),
                boundary_xdmf_path=ctx.get("boundary_xdmf_path"),
                tag_map_path=ctx.get("tag_map_path"),
                tag_legend_path=ctx.get("tag_legend_path"),
                mesh_stats_path=ctx.get("mesh_stats_path"),
                provenance_path=provenance_path,
                solve_report_path=ctx.get("solve_report_path"),
                paraview_state_path=ctx.get("paraview_state_path"),
                paraview_macro_path=ctx.get("paraview_macro_path"),
            )
            self._update_latest_pointer(out_root)

            result = {
                "outputs": ctx.get("output_paths", {}),
                "provenance": provenance_path,
                "artifact_index": artifact_index_path,
                "tag_legend": ctx.get("tag_legend_path"),
                "paraview_state": ctx.get("paraview_state_path"),
                "paraview_macro": ctx.get("paraview_macro_path"),
                "stage_hashes": stage_hashes,
                "stage_records": stage_records,
                "run_hash": self.run_hash(),
                "out_dir": str(out_root),
            }

        broadcast_result = comm.bcast(result, root=0)
        return broadcast_result
