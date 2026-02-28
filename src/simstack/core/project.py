"""Project orchestration and caching hooks (initial scaffolding)."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any, Dict, List

from simstack.config import SimStackConfig, config_to_dict
from simstack.core.artifacts import CadArtifact
from simstack.core.provenance import build_provenance, build_stage_hashes, stable_hash
from simstack.cad.build import build_geometry
from simstack.mesh.mesh_build import GmshSession, build_gmsh_model
from simstack.mesh.import_dolfinx import model_to_mesh, read_from_msh
from simstack.fem.solve import solve_problem
from simstack.io.write import (
    build_tag_fields,
    write_boundary_xdmf,
    write_mesh_xdmf,
    write_outputs,
    write_tag_legend,
)
from simstack.io.paraview import write_paraview_template


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

    def _load_json(self, path: Path) -> Dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        return data

    def _required_output_formats(self) -> List[str]:
        if self.config.outputs.format == "both":
            return ["vtx", "xdmf"]
        return [self.config.outputs.format]

    def _extract_field_paths(self, fields_info: Any) -> Dict[str, Dict[str, str]]:
        paths: Dict[str, Dict[str, str]] = {"vtx": {}, "xdmf": {}}
        if not isinstance(fields_info, dict):
            return paths

        for fmt in ("vtx", "xdmf"):
            fmt_info = fields_info.get(fmt)
            if not isinstance(fmt_info, dict):
                continue
            raw = fmt_info.get("fields")
            if not raw:
                continue
            path = Path(str(raw))
            if path.exists():
                paths[fmt] = {"fields": str(path)}
        return paths

    def _has_required_field_paths(self, paths: Dict[str, Dict[str, str]]) -> bool:
        for fmt in self._required_output_formats():
            if not paths.get(fmt, {}).get("fields"):
                return False
        return True

    def _field_manifest_compatible(self, field_names: Any) -> bool:
        if not self.config.outputs.write_tag_fields:
            return True
        if not isinstance(field_names, list):
            return False
        normalized = [str(name) for name in field_names]
        return "cell_tag" in normalized

    def _find_reusable_stage_artifacts(self, stage_hashes: Dict[str, str], current_out_root: Path) -> Dict[str, Any]:
        base = Path(self.config.outputs.directory)
        if not base.exists():
            return {}

        cad_candidate: tuple[float, Dict[str, Any]] | None = None
        mesh_candidate: tuple[float, Dict[str, Any]] | None = None
        solve_candidate: tuple[float, Dict[str, Any]] | None = None
        post_candidate: tuple[float, Dict[str, Any]] | None = None

        for entry in base.iterdir():
            if not entry.is_dir():
                continue
            if entry.name in {"latest", current_out_root.name}:
                continue

            artifact_index = self._load_json(entry / "reports" / "artifact_index.json")
            if artifact_index is None:
                continue

            index_hashes = artifact_index.get("stage_hashes")
            if not isinstance(index_hashes, dict):
                continue

            source_run_hash = artifact_index.get("run_hash")
            if not source_run_hash:
                source_run_hash = entry.name

            mtime = (entry / "reports" / "artifact_index.json").stat().st_mtime
            artifacts = artifact_index.get("artifacts", {})
            if not isinstance(artifacts, dict):
                artifacts = {}
            fields_info = artifacts.get("fields")
            field_paths = self._extract_field_paths(fields_info)
            field_names = None
            if isinstance(fields_info, dict) and isinstance(fields_info.get("names"), list):
                field_names = [str(name) for name in fields_info.get("names")]

            reports_info = artifacts.get("reports", {})
            if not isinstance(reports_info, dict):
                reports_info = {}
            solve_report_path = None
            raw_solve_report = reports_info.get("solve_report")
            if raw_solve_report:
                solve_report = Path(str(raw_solve_report))
                if solve_report.exists():
                    solve_report_path = str(solve_report)

            if str(index_hashes.get("cad")) == stage_hashes.get("cad"):
                cad_info = artifacts.get("cad", {})
                if isinstance(cad_info, dict):
                    cad_step_path = cad_info.get("step")
                    if cad_step_path:
                        cad_step = Path(str(cad_step_path))
                        if cad_step.exists():
                            cad_payload = {
                                "source_run": str(source_run_hash),
                                "step_path": str(cad_step),
                            }
                            if cad_candidate is None or mtime > cad_candidate[0]:
                                cad_candidate = (mtime, cad_payload)

            if str(index_hashes.get("mesh")) == stage_hashes.get("mesh"):
                mesh_info = artifacts.get("mesh", {})
                if isinstance(mesh_info, dict):
                    mesh_msh_path = mesh_info.get("mesh_msh")
                    tag_map_path = mesh_info.get("tag_map")
                    if mesh_msh_path and tag_map_path:
                        mesh_msh = Path(str(mesh_msh_path))
                        tag_map = Path(str(tag_map_path))
                        if mesh_msh.exists() and tag_map.exists():
                            mesh_payload: Dict[str, Any] = {
                                "source_run": str(source_run_hash),
                                "msh_path": str(mesh_msh),
                                "tag_map_path": str(tag_map),
                            }

                            optional_paths = {
                                "mesh_xdmf_path": mesh_info.get("mesh_xdmf"),
                                "boundary_xdmf_path": mesh_info.get("boundary_xdmf"),
                                "tag_legend_path": mesh_info.get("tag_legend"),
                                "mesh_stats_path": mesh_info.get("mesh_stats"),
                            }
                            for key, raw_path in optional_paths.items():
                                if not raw_path:
                                    continue
                                path_obj = Path(str(raw_path))
                                if path_obj.exists():
                                    mesh_payload[key] = str(path_obj)

                            if mesh_candidate is None or mtime > mesh_candidate[0]:
                                mesh_candidate = (mtime, mesh_payload)

            if str(index_hashes.get("solve")) == stage_hashes.get("solve"):
                if self._has_required_field_paths(field_paths):
                    if self._field_manifest_compatible(field_names):
                        if not self.config.outputs.write_reports or solve_report_path is not None:
                            solve_payload = {
                                "source_run": str(source_run_hash),
                                "fields": field_paths,
                                "field_names": field_names,
                                "solve_report_path": solve_report_path,
                            }
                            if solve_candidate is None or mtime > solve_candidate[0]:
                                solve_candidate = (mtime, solve_payload)

            if str(index_hashes.get("post")) == stage_hashes.get("post"):
                if self._has_required_field_paths(field_paths):
                    if self._field_manifest_compatible(field_names):
                        if not self.config.outputs.write_reports or solve_report_path is not None:
                            post_payload = {
                                "source_run": str(source_run_hash),
                                "fields": field_paths,
                                "field_names": field_names,
                                "solve_report_path": solve_report_path,
                            }
                            if post_candidate is None or mtime > post_candidate[0]:
                                post_candidate = (mtime, post_payload)

        reusable: Dict[str, Any] = {}
        if cad_candidate is not None:
            reusable["cad"] = cad_candidate[1]
        if mesh_candidate is not None:
            reusable["mesh"] = mesh_candidate[1]
        if solve_candidate is not None:
            reusable["solve"] = solve_candidate[1]
        if post_candidate is not None:
            reusable["post"] = post_candidate[1]
        return reusable

    def _copy_artifact_file(self, source_path: str | Path, dest_path: Path) -> str:
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"Reusable artifact path not found: {source}")
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() == dest_path.resolve():
            return str(dest_path)

        if source.is_dir():
            if dest_path.exists():
                if dest_path.is_dir():
                    shutil.rmtree(dest_path)
                else:
                    dest_path.unlink()
            shutil.copytree(source, dest_path)
            return str(dest_path)

        if dest_path.exists() and dest_path.is_dir():
            shutil.rmtree(dest_path)
        shutil.copy2(source, dest_path)
        return str(dest_path)

    def _materialize_reused_cad_step(self, source_step: str, out_root: Path) -> str:
        source = Path(source_step)
        if not source.exists():
            raise FileNotFoundError(f"Reusable CAD STEP path not found: {source}")

        return self._copy_artifact_file(source, out_root / "cad" / source.name)

    def _materialize_reused_mesh_artifacts(self, candidate: Dict[str, Any], out_root: Path) -> Dict[str, str]:
        source_msh = candidate.get("msh_path")
        source_tag_map = candidate.get("tag_map_path")
        if not source_msh or not source_tag_map:
            raise FileNotFoundError("Reusable mesh candidate missing required mesh_msh/tag_map paths")

        mesh_dir = out_root / "mesh"
        mesh_source = Path(str(source_msh))
        materialized = {
            "mesh_msh": self._copy_artifact_file(mesh_source, mesh_dir / mesh_source.name),
            "tag_map": self._copy_artifact_file(str(source_tag_map), mesh_dir / "tag_map.json"),
        }

        optional_sources = {
            "mesh_xdmf_path": "mesh_xdmf",
            "boundary_xdmf_path": "boundary_xdmf",
            "tag_legend_path": "tag_legend",
            "mesh_stats_path": "mesh_stats",
        }
        for key, artifact_name in optional_sources.items():
            raw_path = candidate.get(key)
            if not raw_path:
                continue
            source_path = Path(str(raw_path))
            if not source_path.exists():
                continue
            materialized[artifact_name] = self._copy_artifact_file(source_path, mesh_dir / source_path.name)

        return materialized

    def _materialize_reused_outputs(self, candidate: Dict[str, Any], out_root: Path) -> Dict[str, Dict[str, str]]:
        fields = candidate.get("fields")
        if not isinstance(fields, dict):
            raise FileNotFoundError("Reusable output candidate missing field paths")

        required = self._required_output_formats()
        field_dir = out_root / "fields"
        output_paths: Dict[str, Dict[str, str]] = {"vtx": {}, "xdmf": {}}

        if "vtx" in required:
            vtx_info = fields.get("vtx")
            source_vtx = vtx_info.get("fields") if isinstance(vtx_info, dict) else None
            if not source_vtx:
                raise FileNotFoundError("Reusable output candidate missing vtx field path")
            output_paths["vtx"] = {"fields": self._copy_artifact_file(str(source_vtx), field_dir / "fields.bp")}

        if "xdmf" in required:
            xdmf_info = fields.get("xdmf")
            source_xdmf = xdmf_info.get("fields") if isinstance(xdmf_info, dict) else None
            if not source_xdmf:
                raise FileNotFoundError("Reusable output candidate missing xdmf field path")
            source_xdmf_path = Path(str(source_xdmf))
            copied_xdmf = self._copy_artifact_file(source_xdmf_path, field_dir / "fields.xdmf")
            source_h5_path = source_xdmf_path.with_suffix(".h5")
            if source_h5_path.exists():
                self._copy_artifact_file(source_h5_path, field_dir / "fields.h5")
            output_paths["xdmf"] = {"fields": copied_xdmf}

        return output_paths

    def _write_gmsh_msh(self, out_root: Path) -> str:
        import gmsh

        mesh_dir = out_root / "mesh"
        mesh_dir.mkdir(parents=True, exist_ok=True)
        mesh_msh_path = mesh_dir / "mesh.msh"
        gmsh.write(str(mesh_msh_path))
        return str(mesh_msh_path)

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
        paraview_dir = out_root / "paraview"
        paraview_state_path = paraview_dir / self.config.outputs.paraview_state_name
        paraview_macro_path = paraview_dir / "load_latest.py"

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
        artifact_index_path = out_root / "reports" / "artifact_index.json"
        stage_hashes = self.stage_hashes()
        stage_reuse: Dict[str, Any] = {}
        if self.config.outputs.write_reports:
            if not provenance_path.exists() or not solve_report_path.exists() or not artifact_index_path.exists():
                return None
            data = self._load_json(provenance_path)
            if data is None:
                return None
            if data.get("config_hash") != self.run_hash():
                return None
            artifact_index = self._load_json(artifact_index_path)
            if artifact_index is None:
                return None
            if isinstance(artifact_index, dict):
                index_hashes = artifact_index.get("stage_hashes")
                if isinstance(index_hashes, dict):
                    stage_hashes = {str(k): str(v) for k, v in index_hashes.items()}
                reuse_info = artifact_index.get("reuse")
                if isinstance(reuse_info, dict):
                    stage_reuse = reuse_info
        if self.config.outputs.write_paraview_state:
            if not paraview_state_path.exists() or not paraview_macro_path.exists():
                return None

        return {
            "outputs": outputs,
            "provenance": str(provenance_path) if provenance_path.exists() else None,
            "artifact_index": str(artifact_index_path) if artifact_index_path.exists() else None,
            "tag_legend": str(tag_legend_path) if tag_legend_path.exists() else None,
            "paraview_state": str(paraview_state_path) if paraview_state_path.exists() else None,
            "paraview_macro": str(paraview_macro_path) if paraview_macro_path.exists() else None,
            "stage_hashes": stage_hashes,
            "stage_reuse": stage_reuse,
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

    def _write_artifact_index(
        self,
        out_root: Path,
        *,
        stage_hashes: Dict[str, str],
        cad_step_path: str | None,
        mesh_msh_path: str | None,
        mesh_xdmf_path: str | None,
        boundary_xdmf_path: str | None,
        tag_map_path: str | None,
        tag_legend_path: str | None,
        mesh_stats_path: str | None,
        output_paths: Dict[str, Dict[str, str]],
        field_names: List[str] | None,
        provenance_path: str | None,
        solve_report_path: str | None,
        paraview_state_path: str | None,
        paraview_macro_path: str | None,
        reuse: Dict[str, Any] | None = None,
    ) -> str:
        reports_dir = out_root / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        index_payload = {
            "run_hash": self.run_hash(),
            "stage_hashes": stage_hashes,
            "reuse": reuse or {},
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
        stage_hashes = self.stage_hashes()

        cached = None
        if self.config.outputs.reuse and rank == 0:
            cached = self._load_cached_results(out_root)
            if cached is not None:
                self._update_latest_pointer(out_root)
        cached = comm.bcast(cached, root=0)
        if cached is not None:
            return cached

        stage_reuse_candidates: Dict[str, Any] | None = None
        if rank == 0 and self.config.outputs.reuse:
            stage_reuse_candidates = self._find_reusable_stage_artifacts(stage_hashes, out_root)
        stage_reuse_candidates = comm.bcast(stage_reuse_candidates, root=0)
        if stage_reuse_candidates is None:
            stage_reuse_candidates = {}

        cad_reuse_info: Dict[str, Any] = {"reused": False, "source_run": None, "source_step": None}
        cad_artifact: CadArtifact | None = None
        if rank == 0:
            cad_candidate = stage_reuse_candidates.get("cad")
            if isinstance(cad_candidate, dict):
                source_step = cad_candidate.get("step_path")
                if source_step:
                    reused_step = self._materialize_reused_cad_step(str(source_step), out_root)
                    cad_reuse_info = {
                        "reused": True,
                        "source_run": cad_candidate.get("source_run"),
                        "source_step": str(source_step),
                    }
                    cad_artifact = CadArtifact(
                        shape_ref=None,
                        step_path=reused_step,
                        tag_spec=None,
                        bbox=None,
                        units=self.config.geometry.units,
                        cad_provenance={
                            "builder": self.config.geometry.builder,
                            "params": self.config.geometry.params,
                            "reused": True,
                            "source_run": cad_candidate.get("source_run"),
                        },
                    )

            if cad_artifact is None:
                cad_artifact = build_geometry(self.config.geometry, out_dir=out_root / "cad")
            if cad_artifact.step_path is None:
                raise RuntimeError("CAD builder did not produce a STEP path")
        cad_reuse_info = comm.bcast(cad_reuse_info, root=0)

        mesh_reuse_payload: Dict[str, Any] | None = None
        mesh_reuse_info: Dict[str, Any] = {
            "reused": False,
            "source_run": None,
            "source_msh": None,
            "source_tag_map": None,
        }
        if rank == 0:
            mesh_candidate = stage_reuse_candidates.get("mesh")
            if isinstance(mesh_candidate, dict):
                try:
                    materialized_mesh = self._materialize_reused_mesh_artifacts(mesh_candidate, out_root)
                    reused_tag_map = self._load_json(Path(materialized_mesh["tag_map"]))
                    if reused_tag_map is not None:
                        mesh_reuse_payload = {
                            "mesh_msh": materialized_mesh["mesh_msh"],
                            "tag_map": reused_tag_map,
                        }
                        mesh_stats_path = materialized_mesh.get("mesh_stats")
                        if mesh_stats_path:
                            mesh_stats = self._load_json(Path(mesh_stats_path))
                            if mesh_stats is not None:
                                mesh_reuse_payload["mesh_stats"] = mesh_stats
                        mesh_reuse_info = {
                            "reused": True,
                            "source_run": mesh_candidate.get("source_run"),
                            "source_msh": mesh_candidate.get("msh_path"),
                            "source_tag_map": mesh_candidate.get("tag_map_path"),
                        }
                except FileNotFoundError:
                    mesh_reuse_payload = None
        mesh_reuse_payload = comm.bcast(mesh_reuse_payload, root=0)
        mesh_reuse_info = comm.bcast(mesh_reuse_info, root=0)

        gmsh_result = None
        mesh_msh_path = None
        mesh_stats: Dict[str, Any] | None = None
        tag_map: Dict[str, Any] | None = None

        if mesh_reuse_payload is not None:
            mesh_msh_path = str(mesh_reuse_payload.get("mesh_msh"))
            mesh, cell_tags, facet_tags = read_from_msh(mesh_msh_path, comm)
            reuse_tag_map = mesh_reuse_payload.get("tag_map")
            if isinstance(reuse_tag_map, dict):
                tag_map = reuse_tag_map
            else:
                tag_map = {}
            reuse_mesh_stats = mesh_reuse_payload.get("mesh_stats")
            if isinstance(reuse_mesh_stats, dict):
                mesh_stats = reuse_mesh_stats
        else:
            with GmshSession():
                if rank == 0:
                    gmsh_result = build_gmsh_model(
                        cad_artifact.step_path,
                        self.config.tags,
                        self.config.meshing,
                    )
                    mesh_msh_path = self._write_gmsh_msh(out_root)

                mesh, cell_tags, facet_tags = model_to_mesh(
                    gmsh_result.model if gmsh_result else None,
                    comm,
                    rank=0,
                    gdim=3,
                )

            if gmsh_result is not None:
                tag_map = gmsh_result.tag_result.tag_map
                if gmsh_result.mesh_stats:
                    mesh_stats = gmsh_result.mesh_stats

        tag_map = comm.bcast(tag_map, root=0)
        mesh_msh_path = comm.bcast(mesh_msh_path, root=0)
        if tag_map is None:
            tag_map = {}

        solve_reuse_info: Dict[str, Any] = {
            "reused": False,
            "source_run": None,
            "source_solve_report": None,
        }
        post_reuse_info: Dict[str, Any] = {
            "reused": False,
            "source_run": None,
        }
        reused_output_paths: Dict[str, Dict[str, str]] | None = None
        reused_field_names: List[str] | None = None
        if rank == 0:
            solve_candidate = stage_reuse_candidates.get("solve")
            if isinstance(solve_candidate, dict):
                solve_reuse_info = {
                    "reused": False,
                    "source_run": solve_candidate.get("source_run"),
                    "source_solve_report": solve_candidate.get("solve_report_path"),
                }

            post_candidate = stage_reuse_candidates.get("post")
            candidate_attempts = []
            if isinstance(post_candidate, dict):
                candidate_attempts.append(("post", post_candidate))
            if isinstance(solve_candidate, dict):
                candidate_attempts.append(("solve", solve_candidate))

            for candidate_type, candidate in candidate_attempts:
                try:
                    reused_output_paths = self._materialize_reused_outputs(candidate, out_root)
                    reused_field_names_raw = candidate.get("field_names")
                    if isinstance(reused_field_names_raw, list):
                        reused_field_names = [str(name) for name in reused_field_names_raw]

                    source_solve_report = candidate.get("solve_report_path")
                    if self.config.outputs.write_reports:
                        if not source_solve_report:
                            raise FileNotFoundError("Reusable candidate missing solve report path")
                        self._copy_artifact_file(str(source_solve_report), reports_dir / "solve_report.json")

                    solve_reuse_info = {
                        "reused": True,
                        "source_run": candidate.get("source_run"),
                        "source_solve_report": source_solve_report,
                    }
                    if candidate_type == "post":
                        post_reuse_info = {
                            "reused": True,
                            "source_run": candidate.get("source_run"),
                        }
                    break
                except FileNotFoundError:
                    reused_output_paths = None
                    reused_field_names = None
        reused_output_paths = comm.bcast(reused_output_paths, root=0)
        reused_field_names = comm.bcast(reused_field_names, root=0)
        solve_reuse_info = comm.bcast(solve_reuse_info, root=0)
        post_reuse_info = comm.bcast(post_reuse_info, root=0)

        solve_artifact = None
        field_names: List[str] | None = reused_field_names
        if reused_output_paths is None:
            solve_artifact = solve_problem(
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
            field_names = sorted(fields.keys())
            output_paths = write_outputs(
                mesh,
                fields,
                out_dir=out_root,
                fmt=self.config.outputs.format,
            )
        else:
            output_paths = reused_output_paths

        mesh_xdmf_path = None
        boundary_xdmf_path = None
        if self.config.outputs.write_mesh:
            mesh_xdmf_path = write_mesh_xdmf(mesh, cell_tags, facet_tags, mesh_dir)
            if self.config.outputs.write_boundary_mesh:
                boundary_xdmf_path = write_boundary_xdmf(mesh, facet_tags, mesh_dir)
        tag_legend_path = None
        mesh_stats_file_path = None
        tag_map_path = mesh_dir / "tag_map.json"
        if rank == 0:
            tag_map_path.write_text(json.dumps(tag_map, indent=2, sort_keys=True))
            tag_legend_path = write_tag_legend(tag_map, mesh_dir)
            if mesh_stats is not None:
                mesh_stats_path = mesh_dir / "mesh_stats.json"
                mesh_stats_path.write_text(json.dumps(mesh_stats, indent=2, sort_keys=True))
                mesh_stats_file_path = str(mesh_stats_path)

        provenance_path = None
        report_path = reports_dir / "solve_report.json"
        artifact_index_path = None
        if rank == 0 and self.config.outputs.write_reports:
            provenance_path = self.write_provenance(
                reports_dir,
                tag_map=tag_map,
                mesh_stats=mesh_stats,
                tag_legend_path=tag_legend_path if rank == 0 else None,
                stage_hashes=stage_hashes,
            )
            if reused_output_paths is None:
                report_path.write_text(json.dumps(solve_artifact.solver_report, indent=2, sort_keys=True))

        paraview_state_path = None
        paraview_macro_path = None
        if rank == 0 and self.config.outputs.write_paraview_state:
            paraview_bundle = write_paraview_template(
                out_root,
                output_paths,
                mesh_path=mesh_xdmf_path,
                boundary_path=boundary_xdmf_path,
                tag_map_path=str(tag_map_path) if tag_map_path.exists() else None,
                provenance_path=provenance_path,
                state_name=self.config.outputs.paraview_state_name,
            )
            if paraview_bundle is not None:
                paraview_state_path = paraview_bundle.get("state")
                paraview_macro_path = paraview_bundle.get("macro")

        if rank == 0:
            artifact_index_path = self._write_artifact_index(
                out_root,
                stage_hashes=stage_hashes,
                cad_step_path=cad_artifact.step_path if cad_artifact is not None else None,
                mesh_msh_path=mesh_msh_path,
                mesh_xdmf_path=mesh_xdmf_path,
                boundary_xdmf_path=boundary_xdmf_path,
                tag_map_path=str(tag_map_path) if tag_map_path.exists() else None,
                tag_legend_path=tag_legend_path,
                mesh_stats_path=mesh_stats_file_path,
                output_paths=output_paths,
                field_names=field_names,
                provenance_path=provenance_path,
                solve_report_path=str(report_path) if report_path.exists() else None,
                paraview_state_path=paraview_state_path,
                paraview_macro_path=paraview_macro_path,
                reuse={
                    "cad": cad_reuse_info,
                    "mesh": mesh_reuse_info,
                    "solve": solve_reuse_info,
                    "post": post_reuse_info,
                },
            )
            self._update_latest_pointer(out_root)

        return {
            "outputs": output_paths,
            "provenance": provenance_path,
            "artifact_index": artifact_index_path,
            "tag_legend": str(mesh_dir / "tag_legend.json"),
            "paraview_state": paraview_state_path,
            "paraview_macro": paraview_macro_path,
            "stage_hashes": stage_hashes,
            "stage_reuse": {
                "cad": cad_reuse_info,
                "mesh": mesh_reuse_info,
                "solve": solve_reuse_info,
                "post": post_reuse_info,
            },
            "run_hash": self.run_hash(),
            "out_dir": str(out_root),
        }
