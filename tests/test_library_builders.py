from __future__ import annotations

from pathlib import Path

import pytest

from simstack.config import GeometryConfig
from simstack.cad.build import build_geometry


@pytest.mark.parametrize(
    ("builder", "params"),
    [
        ("qfn", {"body_x": 5.0, "body_y": 5.0, "leads_per_side": 10}),
        ("rgy0020d", {"body_x": 3.5, "body_y": 4.5}),
        ("w61700", {"bore_diameter": 10.0, "outer_diameter": 15.0}),
    ],
)
def test_library_builder_exports_step(tmp_path: Path, builder: str, params: dict[str, float]) -> None:
    geometry = GeometryConfig.model_validate(
        {
            "builder": builder,
            "params": params,
            "units": "mm",
        }
    )

    artifact = build_geometry(geometry, out_dir=tmp_path / builder)
    assert artifact.step_path is not None
    assert Path(artifact.step_path).exists()
