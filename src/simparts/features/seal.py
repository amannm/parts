from __future__ import annotations

from dataclasses import dataclass

import cadquery as cq


@dataclass(frozen=True)
class SealSpec:
    inner_diameter: float
    outer_diameter: float
    thickness: float
    axial_offset: float = 0.0


def _validate_seal(spec: SealSpec) -> None:
    if spec.inner_diameter <= 0:
        raise ValueError("Seal inner diameter must be positive.")
    if spec.outer_diameter <= spec.inner_diameter:
        raise ValueError("Seal outer diameter must be greater than inner diameter.")
    if spec.thickness <= 0:
        raise ValueError("Seal thickness must be positive.")


def build_seal(spec: SealSpec) -> cq.Workplane:
    _validate_seal(spec)
    inner_radius = spec.inner_diameter / 2.0
    outer_radius = spec.outer_diameter / 2.0
    seal = (
        cq.Workplane("XY")
        .circle(outer_radius)
        .circle(inner_radius)
        .extrude(spec.thickness, both=True)
    )
    if spec.axial_offset != 0.0:
        seal = seal.translate((0, 0, spec.axial_offset))
    return seal
