"""CAD builders (CadQuery integration)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict

from simstack.config import GeometryConfig
from simstack.core.artifacts import CadArtifact


Builder = Callable[[Dict[str, Any]], Any]
_BUILDERS: Dict[str, Builder] = {}


def register_builder(name: str) -> Callable[[Builder], Builder]:
    def decorator(func: Builder) -> Builder:
        _BUILDERS[name] = func
        return func

    return decorator


@register_builder("block_with_hole")
def _build_block_with_hole(params: Dict[str, Any]) -> Any:
    import cadquery as cq

    length = float(params.get("length", 1.0))
    width = float(params.get("width", 1.0))
    height = float(params.get("height", 1.0))
    hole_radius = float(params.get("hole_radius", 0.0))

    wp = cq.Workplane("XY").box(length, width, height)
    if hole_radius > 0:
        wp = wp.faces(">Z").workplane().hole(2 * hole_radius)
    return wp


def _export_step(shape: Any, out_dir: Path, name: str) -> Path:
    import cadquery as cq

    out_dir.mkdir(parents=True, exist_ok=True)
    step_path = out_dir / f"{name}.step"
    cq.exporters.export(shape, str(step_path))
    return step_path


def build_geometry(geometry: GeometryConfig, out_dir: str | Path | None = None) -> CadArtifact:
    if geometry.builder not in _BUILDERS:
        raise KeyError(f"Unknown CAD builder: {geometry.builder}")

    builder = _BUILDERS[geometry.builder]
    shape = builder(geometry.params)

    step_path: Path | None = None
    if out_dir is not None:
        step_path = _export_step(shape, Path(out_dir), geometry.builder)

    return CadArtifact(
        shape_ref=shape,
        step_path=str(step_path) if step_path else None,
        tag_spec=None,
        bbox=None,
        units=geometry.units,
        cad_provenance={"builder": geometry.builder, "params": geometry.params},
    )
