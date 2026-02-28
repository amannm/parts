from __future__ import annotations

from dataclasses import dataclass

import cadquery as cq


@dataclass(frozen=True)
class InnerRingSpec:
    bore_diameter: float
    outer_diameter: float
    width: float
    groove_radius: float
    groove_depth: float
    chamfer: float = 0.0


def _validate_inner_ring(spec: InnerRingSpec) -> None:
    if spec.bore_diameter <= 0:
        raise ValueError("Inner ring bore diameter must be positive.")
    if spec.outer_diameter <= spec.bore_diameter:
        raise ValueError("Inner ring outer diameter must be greater than bore diameter.")
    if spec.width <= 0:
        raise ValueError("Inner ring width must be positive.")
    if spec.groove_radius <= 0:
        raise ValueError("Inner ring groove radius must be positive.")
    if spec.groove_depth <= 0:
        raise ValueError("Inner ring groove depth must be positive.")
    if spec.chamfer < 0:
        raise ValueError("Inner ring chamfer must be non-negative.")
    wall_thickness = (spec.outer_diameter - spec.bore_diameter) / 2.0
    if spec.groove_depth >= wall_thickness:
        raise ValueError("Inner ring groove depth must be less than wall thickness.")


def build_inner_ring(spec: InnerRingSpec) -> cq.Workplane:
    _validate_inner_ring(spec)
    bore_radius = spec.bore_diameter / 2.0
    outer_radius = spec.outer_diameter / 2.0
    half_width = spec.width / 2.0
    ring = (
        cq.Workplane("XY")
        .circle(outer_radius)
        .circle(bore_radius)
        .extrude(spec.width, both=True)
    )
    if spec.chamfer > 0:
        max_chamfer = min(
            (spec.outer_diameter - spec.bore_diameter) / 4.0,
            half_width * 0.4,
        )
        c = min(spec.chamfer, max_chamfer)
        try:
            ring = ring.faces(">Z or <Z").edges().chamfer(c)
        except Exception:
            print("WARN: Inner ring chamfer failed (try smaller chamfer).")
    groove_center_r = outer_radius - spec.groove_depth + spec.groove_radius
    groove_cutter = cq.Workplane("XY").add(
        cq.Solid.makeTorus(groove_center_r, spec.groove_radius)
    )
    ring = ring.cut(groove_cutter)
    return ring
