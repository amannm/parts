from __future__ import annotations

from pathlib import Path

from simstack.config import load_sweep_config
from simstack.sweep import run_sweep


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_rotor_angle_sweep_dry_run(tmp_path: Path) -> None:
    sweep_cfg = load_sweep_config(REPO_ROOT / "examples" / "configs" / "rotor_angle_sweep.yaml")
    summary = run_sweep(
        sweep_cfg,
        repo_root=REPO_ROOT,
        dry_run=True,
        out_dir=str(tmp_path / "sweep"),
    )

    assert summary["count"] == 4
    assert Path(summary["report_path"]).exists()
    for run in summary["runs"]:
        assert Path(run["dry_run_report"]).exists()
