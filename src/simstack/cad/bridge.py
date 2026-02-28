"""CAD bridge helpers.

v1 bridge: CadQuery/OCC shape -> STEP file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def export_step(shape: Any, out_dir: str | Path, name: str) -> Path:
    import cadquery as cq
    from cadquery.occ_impl.exporters import assembly as asm_export

    path = Path(out_dir)
    path.mkdir(parents=True, exist_ok=True)

    step_path = path / f"{name}.step"
    if isinstance(shape, cq.Assembly):
        asm_export.exportAssembly(shape, str(step_path))
    else:
        cq.exporters.export(shape, str(step_path))
    return step_path


def ensure_step_exists(step_path: str | Path) -> Path:
    path = Path(step_path)
    if not path.exists():
        raise FileNotFoundError(f"STEP file not found: {path}")
    return path
