from __future__ import annotations

from pathlib import Path
from typing import Iterable, Protocol

import cadquery as cq
from cadquery.occ_impl.exporters import assembly as asm_export


class BodyParams(Protocol):
    body_x: float
    body_y: float
    body_height: float


def _resolve_standoff(params: BodyParams, standoff: float | None) -> float:
    if standoff is not None:
        return standoff
    return getattr(params, "standoff", 0.0)


def build_body(
    params: BodyParams,
    *,
    standoff: float | None = None,
    fillet: float = 0.0,
) -> cq.Workplane:
    standoff_value = _resolve_standoff(params, standoff)
    body_thickness = params.body_height - standoff_value
    body = cq.Workplane("XY").box(params.body_x, params.body_y, body_thickness)
    if fillet > 0:
        body = body.edges("|Z").fillet(fillet)
    return body.translate((0, 0, standoff_value + body_thickness / 2))


def square_pin1_marker(
    *,
    center_x: float,
    center_y: float,
    body_height: float,
    size: float,
    depth: float,
) -> cq.Workplane:
    return (
        cq.Workplane("XY")
        .workplane(offset=body_height)
        .moveTo(center_x, center_y)
        .rect(size, size)
        .extrude(-depth)
    )


def circular_pin1_marker(
    *,
    center_x: float,
    center_y: float,
    body_height: float,
    diameter: float,
    depth: float,
) -> cq.Workplane:
    return (
        cq.Workplane("XY")
        .workplane(offset=body_height)
        .moveTo(center_x, center_y)
        .circle(diameter / 2)
        .extrude(-depth)
    )


def union_solids(solids: Iterable[cq.Workplane]) -> cq.Workplane | None:
    result = None
    for solid in solids:
        result = solid if result is None else result.union(solid)
    return result


def export_step(model: cq.Workplane | cq.Assembly, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(model, cq.Assembly):
        asm_export.exportAssembly(model, str(out_path))
    else:
        cq.exporters.export(model, str(out_path))
