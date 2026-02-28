from __future__ import annotations

import json
from pathlib import Path

from simstack.config import SimStackConfig
from simstack.core.project import Project


def _make_project(
    tmp_path: Path,
    length: float = 1.0,
    fmt: str = "vtx",
    write_tag_fields: bool = True,
) -> Project:
    config = SimStackConfig.model_validate(
        {
            "geometry": {
                "builder": "block_with_hole",
                "params": {"length": length, "width": 1.0, "height": 1.0},
            },
            "physics": {"model": "poisson", "parameters": {"source": 0.0}},
            "outputs": {
                "directory": str(tmp_path / "out"),
                "format": fmt,
                "write_tag_fields": write_tag_fields,
            },
        }
    )
    return Project(config, repo_root=tmp_path)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_find_reusable_stage_artifacts_returns_matching_cad_step(tmp_path: Path) -> None:
    project = _make_project(tmp_path, length=1.0)
    stage_hashes = project.stage_hashes()
    current_out = project.output_root()

    previous_run = Path(project.config.outputs.directory) / "prev_run"
    cad_step = previous_run / "cad" / "block_with_hole.step"
    _write_text(cad_step, "step-data")
    artifact_index = {
        "run_hash": "prev_run",
        "stage_hashes": stage_hashes,
        "artifacts": {"cad": {"step": str(cad_step)}},
    }
    _write_text(previous_run / "reports" / "artifact_index.json", json.dumps(artifact_index))

    reusable = project._find_reusable_stage_artifacts(stage_hashes, current_out)
    assert reusable["cad"]["source_run"] == "prev_run"
    assert reusable["cad"]["step_path"] == str(cad_step)


def test_find_reusable_stage_artifacts_returns_matching_mesh_bundle(tmp_path: Path) -> None:
    project = _make_project(tmp_path, length=1.0)
    stage_hashes = project.stage_hashes()
    current_out = project.output_root()

    previous_run = Path(project.config.outputs.directory) / "prev_mesh"
    mesh_msh = previous_run / "mesh" / "mesh.msh"
    tag_map = previous_run / "mesh" / "tag_map.json"
    mesh_stats = previous_run / "mesh" / "mesh_stats.json"
    _write_text(mesh_msh, "$MeshFormat\n")
    _write_text(tag_map, json.dumps({"facets": {"left": 1}, "cells": {"domain": 2}}))
    _write_text(mesh_stats, json.dumps({"min_quality": 0.7}))
    artifact_index = {
        "run_hash": "prev_mesh",
        "stage_hashes": stage_hashes,
        "artifacts": {
            "mesh": {
                "mesh_msh": str(mesh_msh),
                "tag_map": str(tag_map),
                "mesh_stats": str(mesh_stats),
            }
        },
    }
    _write_text(previous_run / "reports" / "artifact_index.json", json.dumps(artifact_index))

    reusable = project._find_reusable_stage_artifacts(stage_hashes, current_out)
    assert reusable["mesh"]["source_run"] == "prev_mesh"
    assert reusable["mesh"]["msh_path"] == str(mesh_msh)
    assert reusable["mesh"]["tag_map_path"] == str(tag_map)
    assert reusable["mesh"]["mesh_stats_path"] == str(mesh_stats)


def test_materialize_reused_mesh_artifacts_copies_required_files(tmp_path: Path) -> None:
    project = _make_project(tmp_path, length=1.0)

    source_root = tmp_path / "source_run"
    mesh_msh = source_root / "mesh" / "mesh.msh"
    tag_map = source_root / "mesh" / "tag_map.json"
    mesh_stats = source_root / "mesh" / "mesh_stats.json"
    _write_text(mesh_msh, "$MeshFormat\n")
    _write_text(tag_map, json.dumps({"facets": {"left": 1}, "cells": {"domain": 2}}))
    _write_text(mesh_stats, json.dumps({"min_quality": 0.8}))

    materialized = project._materialize_reused_mesh_artifacts(
        {
            "msh_path": str(mesh_msh),
            "tag_map_path": str(tag_map),
            "mesh_stats_path": str(mesh_stats),
        },
        project.output_root(),
    )

    assert Path(materialized["mesh_msh"]).exists()
    assert Path(materialized["tag_map"]).exists()
    assert Path(materialized["mesh_stats"]).exists()
    assert json.loads(Path(materialized["tag_map"]).read_text())["facets"]["left"] == 1


def test_find_reusable_stage_artifacts_returns_matching_solve_and_post_bundle(tmp_path: Path) -> None:
    project = _make_project(tmp_path, length=1.0, fmt="vtx")
    stage_hashes = project.stage_hashes()
    current_out = project.output_root()

    previous_run = Path(project.config.outputs.directory) / "prev_post"
    fields_bp = previous_run / "fields" / "fields.bp"
    solve_report = previous_run / "reports" / "solve_report.json"
    _write_text(fields_bp, "bp-data")
    _write_text(solve_report, json.dumps({"iterations": 12}))
    artifact_index = {
        "run_hash": "prev_post",
        "stage_hashes": stage_hashes,
        "artifacts": {
            "fields": {"vtx": {"fields": str(fields_bp)}, "xdmf": {}, "names": ["u", "cell_tag"]},
            "reports": {"solve_report": str(solve_report)},
        },
    }
    _write_text(previous_run / "reports" / "artifact_index.json", json.dumps(artifact_index))

    reusable = project._find_reusable_stage_artifacts(stage_hashes, current_out)
    assert reusable["solve"]["source_run"] == "prev_post"
    assert reusable["solve"]["fields"]["vtx"]["fields"] == str(fields_bp)
    assert reusable["post"]["source_run"] == "prev_post"
    assert reusable["post"]["solve_report_path"] == str(solve_report)


def test_find_reusable_stage_artifacts_solve_match_without_post_match(tmp_path: Path) -> None:
    current = _make_project(tmp_path, length=1.0, fmt="vtx")
    stage_hashes = current.stage_hashes()
    current_out = current.output_root()

    other = _make_project(tmp_path, length=1.0, fmt="xdmf")
    other_hashes = other.stage_hashes()

    previous_run = Path(current.config.outputs.directory) / "prev_solve_only"
    fields_bp = previous_run / "fields" / "fields.bp"
    solve_report = previous_run / "reports" / "solve_report.json"
    _write_text(fields_bp, "bp-data")
    _write_text(solve_report, "{}")
    artifact_index = {
        "run_hash": "prev_solve_only",
        "stage_hashes": other_hashes,
        "artifacts": {
            "fields": {"vtx": {"fields": str(fields_bp)}, "xdmf": {}, "names": ["u", "cell_tag"]},
            "reports": {"solve_report": str(solve_report)},
        },
    }
    _write_text(previous_run / "reports" / "artifact_index.json", json.dumps(artifact_index))

    reusable = current._find_reusable_stage_artifacts(stage_hashes, current_out)
    assert "solve" in reusable
    assert "post" not in reusable
    assert reusable["solve"]["source_run"] == "prev_solve_only"


def test_find_reusable_stage_artifacts_requires_field_manifest_when_tag_field_enabled(tmp_path: Path) -> None:
    project = _make_project(tmp_path, length=1.0, fmt="vtx", write_tag_fields=True)
    stage_hashes = project.stage_hashes()
    current_out = project.output_root()

    previous_run = Path(project.config.outputs.directory) / "prev_no_manifest"
    fields_bp = previous_run / "fields" / "fields.bp"
    solve_report = previous_run / "reports" / "solve_report.json"
    _write_text(fields_bp, "bp-data")
    _write_text(solve_report, "{}")
    artifact_index = {
        "run_hash": "prev_no_manifest",
        "stage_hashes": stage_hashes,
        "artifacts": {
            "fields": {"vtx": {"fields": str(fields_bp)}, "xdmf": {}},
            "reports": {"solve_report": str(solve_report)},
        },
    }
    _write_text(previous_run / "reports" / "artifact_index.json", json.dumps(artifact_index))

    reusable = project._find_reusable_stage_artifacts(stage_hashes, current_out)
    assert "solve" not in reusable
    assert "post" not in reusable


def test_find_reusable_stage_artifacts_allows_missing_manifest_when_tag_field_disabled(tmp_path: Path) -> None:
    project = _make_project(tmp_path, length=1.0, fmt="vtx", write_tag_fields=False)
    stage_hashes = project.stage_hashes()
    current_out = project.output_root()

    previous_run = Path(project.config.outputs.directory) / "prev_no_manifest_no_tags"
    fields_bp = previous_run / "fields" / "fields.bp"
    solve_report = previous_run / "reports" / "solve_report.json"
    _write_text(fields_bp, "bp-data")
    _write_text(solve_report, "{}")
    artifact_index = {
        "run_hash": "prev_no_manifest_no_tags",
        "stage_hashes": stage_hashes,
        "artifacts": {
            "fields": {"vtx": {"fields": str(fields_bp)}, "xdmf": {}},
            "reports": {"solve_report": str(solve_report)},
        },
    }
    _write_text(previous_run / "reports" / "artifact_index.json", json.dumps(artifact_index))

    reusable = project._find_reusable_stage_artifacts(stage_hashes, current_out)
    assert reusable["solve"]["source_run"] == "prev_no_manifest_no_tags"
    assert reusable["post"]["source_run"] == "prev_no_manifest_no_tags"


def test_materialize_reused_outputs_copies_vtx_directory(tmp_path: Path) -> None:
    project = _make_project(tmp_path, length=1.0, fmt="vtx")
    source_bp_dir = tmp_path / "source_run" / "fields" / "fields.bp"
    (source_bp_dir / "subdir").mkdir(parents=True, exist_ok=True)
    _write_text(source_bp_dir / "subdir" / "meta.txt", "ok")

    output_paths = project._materialize_reused_outputs(
        {"fields": {"vtx": {"fields": str(source_bp_dir)}, "xdmf": {}}},
        project.output_root(),
    )

    copied = Path(output_paths["vtx"]["fields"])
    assert copied.is_dir()
    assert (copied / "subdir" / "meta.txt").read_text() == "ok"


def test_materialize_reused_outputs_copies_xdmf_with_h5_sidecar(tmp_path: Path) -> None:
    project = _make_project(tmp_path, length=1.0, fmt="xdmf")
    source_fields_dir = tmp_path / "source_run" / "fields"
    source_xdmf = source_fields_dir / "fields.xdmf"
    source_h5 = source_fields_dir / "fields.h5"
    _write_text(source_xdmf, "<Xdmf/>")
    _write_text(source_h5, "hdf5-data")

    output_paths = project._materialize_reused_outputs(
        {"fields": {"vtx": {}, "xdmf": {"fields": str(source_xdmf)}}},
        project.output_root(),
    )

    copied_xdmf = Path(output_paths["xdmf"]["fields"])
    copied_h5 = copied_xdmf.with_suffix(".h5")
    assert copied_xdmf.exists()
    assert copied_h5.exists()
    assert copied_h5.read_text() == "hdf5-data"


def test_find_reusable_stage_artifacts_ignores_mismatched_hash(tmp_path: Path) -> None:
    current = _make_project(tmp_path, length=1.0)
    stage_hashes = current.stage_hashes()
    current_out = current.output_root()

    other = _make_project(tmp_path, length=3.0)
    other_hashes = other.stage_hashes()

    previous_run = Path(current.config.outputs.directory) / "prev_other"
    cad_step = previous_run / "cad" / "block_with_hole.step"
    _write_text(cad_step, "step-data")
    artifact_index = {
        "run_hash": "prev_other",
        "stage_hashes": other_hashes,
        "artifacts": {"cad": {"step": str(cad_step)}},
    }
    _write_text(previous_run / "reports" / "artifact_index.json", json.dumps(artifact_index))

    reusable = current._find_reusable_stage_artifacts(stage_hashes, current_out)
    assert reusable == {}
