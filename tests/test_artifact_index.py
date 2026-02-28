from __future__ import annotations

import json
from pathlib import Path

from simstack.config import SimStackConfig
from simstack.core.project import Project


def _make_project(tmp_path: Path) -> Project:
    config = SimStackConfig.model_validate(
        {
            "geometry": {
                "builder": "block_with_hole",
                "params": {"length": 1.0, "width": 1.0, "height": 1.0},
            },
            "physics": {"model": "poisson", "parameters": {}},
            "outputs": {"directory": str(tmp_path / "out"), "format": "vtx"},
        }
    )
    return Project(config, repo_root=tmp_path)


def test_write_artifact_index_contains_stage_hashes_and_paths(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    out_root = project.output_root()
    out_root.mkdir(parents=True, exist_ok=True)

    output_paths = {"vtx": {"fields": str(out_root / "fields" / "fields.bp")}, "xdmf": {}}
    stage_hashes = project.stage_hashes()

    path = project._write_artifact_index(
        out_root,
        stage_hashes=stage_hashes,
        cad_step_path=str(out_root / "cad" / "block_with_hole.step"),
        mesh_msh_path=str(out_root / "mesh" / "mesh.msh"),
        mesh_xdmf_path=str(out_root / "mesh" / "mesh.xdmf"),
        boundary_xdmf_path=str(out_root / "mesh" / "boundary.xdmf"),
        tag_map_path=str(out_root / "mesh" / "tag_map.json"),
        tag_legend_path=str(out_root / "mesh" / "tag_legend.json"),
        mesh_stats_path=str(out_root / "mesh" / "mesh_stats.json"),
        output_paths=output_paths,
        field_names=["u", "cell_tag"],
        provenance_path=str(out_root / "reports" / "provenance.json"),
        solve_report_path=str(out_root / "reports" / "solve_report.json"),
        paraview_state_path=str(out_root / "paraview" / "latest.pvsm"),
        paraview_macro_path=str(out_root / "paraview" / "load_latest.py"),
    )

    payload = json.loads(Path(path).read_text())
    assert payload["run_hash"] == project.run_hash()
    assert payload["stage_hashes"] == stage_hashes
    assert payload["reuse"] == {}
    assert payload["artifacts"]["cad"]["step"].endswith(".step")
    assert payload["artifacts"]["mesh"]["mesh_msh"].endswith(".msh")
    assert payload["artifacts"]["mesh"]["mesh_stats"].endswith(".json")
    assert payload["artifacts"]["fields"]["vtx"] == output_paths["vtx"]
    assert payload["artifacts"]["fields"]["xdmf"] == output_paths["xdmf"]
    assert payload["artifacts"]["fields"]["names"] == ["u", "cell_tag"]
