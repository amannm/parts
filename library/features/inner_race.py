from __future__ import annotations

from dataclasses import dataclass

import cadquery as cq


@dataclass(frozen=True)
class InnerRaceSpec:
    bore_diameter: float
    outer_diameter: float
    width: float
    groove_radius: float
    groove_depth: float
    chamfer: float = 0.0


def _validate_inner_race(spec: InnerRaceSpec) -> None:
    if spec.bore_diameter <= 0:
        raise ValueError("Inner race bore diameter must be positive.")
    if spec.outer_diameter <= spec.bore_diameter:
        raise ValueError("Inner race outer diameter must be greater than bore diameter.")
    if spec.width <= 0:
        raise ValueError("Inner race width must be positive.")
    if spec.groove_radius <= 0:
        raise ValueError("Inner race groove radius must be positive.")
    if spec.groove_depth <= 0:
        raise ValueError("Inner race groove depth must be positive.")
    if spec.chamfer < 0:
        raise ValueError("Inner race chamfer must be non-negative.")
    wall_thickness = (spec.outer_diameter - spec.bore_diameter) / 2.0
    if spec.groove_depth >= wall_thickness:
        raise ValueError("Inner race groove depth must be less than wall thickness.")


def build_inner_race(spec: InnerRaceSpec) -> cq.Workplane:
    _validate_inner_race(spec)
    bore_radius = spec.bore_diameter / 2.0
    outer_radius = spec.outer_diameter / 2.0
    half_width = spec.width / 2.0
    race = (
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
            race = race.faces(">Z or <Z").edges().chamfer(c)
        except Exception:
            print("WARN: Inner race chamfer failed (try smaller chamfer).")
    groove_center_r = outer_radius - spec.groove_depth + spec.groove_radius
    groove_cutter = (
        cq.Workplane("XZ")
        .transformed(offset=(groove_center_r, 0, 0))
        .circle(spec.groove_radius)
        .revolve(360, (0, 0, 0), (0, 0, 1))
    )
    race = race.cut(groove_cutter)
    return race
