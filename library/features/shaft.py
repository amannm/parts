from __future__ import annotations

from dataclasses import dataclass

import cadquery as cq


@dataclass(frozen=True)
class ShaftSpec:
    diameter: float
    length: float
    bore_diameter: float = 0.0
    chamfer: float = 0.0
    centered: bool = True
    flat_depth: float = 0.0
    flat_width: float = 0.0
    flat_angle_deg: float = 0.0
    keyway_width: float = 0.0
    keyway_depth: float = 0.0
    keyway_length: float = 0.0
    keyway_angle_deg: float = 0.0


def _validate_shaft(spec: ShaftSpec) -> None:
    if spec.diameter <= 0:
        raise ValueError("Shaft diameter must be positive.")
    if spec.length <= 0:
        raise ValueError("Shaft length must be positive.")
    if spec.bore_diameter < 0:
        raise ValueError("Shaft bore diameter must be non-negative.")
    if spec.bore_diameter >= spec.diameter:
        raise ValueError("Shaft bore diameter must be smaller than shaft diameter.")
    if spec.chamfer < 0:
        raise ValueError("Shaft chamfer must be non-negative.")
    if spec.flat_depth < 0:
        raise ValueError("Shaft flat depth must be non-negative.")
    if spec.flat_width < 0:
        raise ValueError("Shaft flat width must be non-negative.")
    if spec.keyway_width < 0:
        raise ValueError("Shaft keyway width must be non-negative.")
    if spec.keyway_depth < 0:
        raise ValueError("Shaft keyway depth must be non-negative.")
    if spec.keyway_length < 0:
        raise ValueError("Shaft keyway length must be non-negative.")
    radius = spec.diameter / 2.0
    if spec.flat_depth >= radius and spec.flat_depth > 0:
        raise ValueError("Shaft flat depth must be smaller than shaft radius.")
    if spec.keyway_depth >= radius and spec.keyway_depth > 0:
        raise ValueError("Shaft keyway depth must be smaller than shaft radius.")
    if spec.keyway_depth > 0 and spec.keyway_width <= 0:
        raise ValueError("Shaft keyway width must be positive when keyway depth is set.")
    if spec.keyway_length > spec.length:
        raise ValueError("Shaft keyway length cannot exceed shaft length.")


def _axial_center(length: float, centered: bool) -> float:
    return 0.0 if centered else length / 2.0


def _flat_cutter(spec: ShaftSpec, *, radius: float) -> cq.Workplane | None:
    if spec.flat_depth <= 0:
        return None
    flat_width = spec.flat_width if spec.flat_width > 0 else spec.diameter * 2.0
    box_y = spec.diameter * 2.0
    y_center = radius - spec.flat_depth + box_y / 2.0
    z_center = _axial_center(spec.length, spec.centered)
    cutter = (
        cq.Workplane("XY")
        .box(flat_width, box_y, spec.length, centered=(True, True, True))
        .translate((0, y_center, z_center))
    )
    if spec.flat_angle_deg != 0:
        cutter = cutter.rotate((0, 0, 0), (0, 0, 1), spec.flat_angle_deg)
    return cutter


def _keyway_cutter(spec: ShaftSpec, *, radius: float) -> cq.Workplane | None:
    if spec.keyway_depth <= 0 or spec.keyway_width <= 0:
        return None
    keyway_len = spec.keyway_length if spec.keyway_length > 0 else spec.length
    z_center = _axial_center(spec.length, spec.centered)
    y_center = radius - spec.keyway_depth / 2.0
    cutter = (
        cq.Workplane("XY")
        .box(spec.keyway_width, spec.keyway_depth, keyway_len, centered=(True, True, True))
        .translate((0, y_center, z_center))
    )
    if spec.keyway_angle_deg != 0:
        cutter = cutter.rotate((0, 0, 0), (0, 0, 1), spec.keyway_angle_deg)
    return cutter


def build_shaft(spec: ShaftSpec) -> cq.Workplane:
    _validate_shaft(spec)
    radius = spec.diameter / 2.0
    shaft = cq.Workplane("XY").circle(radius).extrude(spec.length, both=spec.centered)
    if spec.bore_diameter > 0:
        bore = (
            cq.Workplane("XY")
            .circle(spec.bore_diameter / 2.0)
            .extrude(spec.length, both=spec.centered)
        )
        shaft = shaft.cut(bore)
    flat_cutter = _flat_cutter(spec, radius=radius)
    if flat_cutter is not None:
        shaft = shaft.cut(flat_cutter)
    keyway_cutter = _keyway_cutter(spec, radius=radius)
    if keyway_cutter is not None:
        shaft = shaft.cut(keyway_cutter)
    if spec.chamfer > 0:
        max_chamfer = min(radius, spec.length / 2.0) * 0.99
        c = min(spec.chamfer, max_chamfer)
        try:
            shaft = shaft.edges("|Z").chamfer(c)
        except Exception:
            print("WARN: Shaft chamfer failed (try smaller chamfer).")
    return shaft
