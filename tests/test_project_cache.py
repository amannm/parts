from __future__ import annotations

import json
from pathlib import Path

from simstack.config import SimStackConfig
from simstack.core.project import Project


def _make_config() -> SimStackConfig:
    return SimStackConfig.model_validate(
        {
            "geometry": {
                "builder": "block_with_hole",
                "params": {"length": 1.0, "width": 1.0, "height": 1.0},
            },
            "physics": {"model": "poisson", "parameters": {}},
            "outputs": {
                "directory": "out",
                "format": "vtx",
                "write_mesh": True,
                "write_reports": True,
                "write_boundary_mesh": True,
                "write_paraview_state": True,
            },
        }
    )


def _write_text(path: Path, content: str = "ok") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _materialize_cached_layout(project: Project, out_root: Path) -> None:
    stage_hashes = project.stage_hashes()
    _write_text(out_root / "fields" / "fields.bp")
    _write_text(out_root / "mesh" / "mesh.xdmf")
    _write_text(out_root / "mesh" / "boundary.xdmf")
    _write_text(out_root / "mesh" / "tag_map.json", "{}")
    _write_text(out_root / "mesh" / "tag_legend.json", "{}")
    _write_text(out_root / "reports" / "solve_report.json", "{}")
    _write_text(
        out_root / "reports" / "provenance.json",
        json.dumps({"config_hash": project.run_hash()}),
    )
    _write_text(
        out_root / "reports" / "artifact_index.json",
        json.dumps({"stage_hashes": stage_hashes, "reuse": {"cad": {"reused": False}}}),
    )
    _write_text(out_root / "paraview" / "latest.pvsm", "<template />")
    _write_text(out_root / "paraview" / "load_latest.py", "print('ok')\n")


def test_load_cached_results_accepts_complete_layout(tmp_path: Path) -> None:
    config = _make_config()
    project = Project(config, repo_root=tmp_path)
    out_root = project.output_root()

    _materialize_cached_layout(project, out_root)
    cached = project._load_cached_results(out_root)

    assert cached is not None
    assert cached["cached"] is True
    assert cached["artifact_index"].endswith("artifact_index.json")
    assert cached["paraview_state"].endswith("latest.pvsm")
    assert cached["paraview_macro"].endswith("load_latest.py")
    assert cached["stage_hashes"] == project.stage_hashes()
    assert cached["stage_reuse"] == {"cad": {"reused": False}}


def test_load_cached_results_requires_paraview_when_enabled(tmp_path: Path) -> None:
    config = _make_config()
    project = Project(config, repo_root=tmp_path)
    out_root = project.output_root()

    _materialize_cached_layout(project, out_root)
    (out_root / "paraview" / "latest.pvsm").unlink()

    assert project._load_cached_results(out_root) is None
