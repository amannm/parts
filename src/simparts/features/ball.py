from __future__ import annotations

from dataclasses import dataclass

import cadquery as cq


@dataclass(frozen=True)
class BallSpec:
    diameter: float


def _validate_ball(spec: BallSpec) -> None:
    if spec.diameter <= 0:
        raise ValueError("Ball diameter must be positive.")


def build_ball(spec: BallSpec) -> cq.Workplane:
    _validate_ball(spec)
    radius = spec.diameter / 2.0
    ball = cq.Workplane("XY").sphere(radius)
    return ball
