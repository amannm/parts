
from __future__ import annotations

import math
from dataclasses import dataclass

import cadquery as cq


@dataclass(frozen=True)
class CageSpec:
    pitch_diameter: float
    ball_diameter: float
    num_balls: int
    width: float
    wall_thickness: float


def _validate_cage(spec: CageSpec) -> None:
    if spec.pitch_diameter <= 0:
        raise ValueError("Cage pitch diameter must be positive.")
    if spec.ball_diameter <= 0:
        raise ValueError("Cage ball diameter must be positive.")
    if spec.num_balls < 3:
        raise ValueError("Cage must have at least 3 balls.")
    if spec.width <= 0:
        raise ValueError("Cage width must be positive.")
    if spec.wall_thickness <= 0:
        raise ValueError("Cage wall thickness must be positive.")
    if spec.ball_diameter >= spec.width:
        raise ValueError("Ball diameter must be less than cage width.")


def build_cage(spec: CageSpec) -> cq.Workplane:
    _validate_cage(spec)
    pitch_radius = spec.pitch_diameter / 2.0
    ball_radius = spec.ball_diameter / 2.0
    inner_radius = pitch_radius - ball_radius - spec.wall_thickness
    outer_radius = pitch_radius + ball_radius + spec.wall_thickness
    half_width = spec.width / 2.0
    cage = (
        cq.Workplane("XY")
        .circle(outer_radius)
        .circle(inner_radius)
        .extrude(spec.width, both=True)
    )
    pocket_radius = ball_radius * 1.05
    angle_step = 360.0 / spec.num_balls
    for i in range(spec.num_balls):
        angle_rad = math.radians(i * angle_step)
        x = pitch_radius * math.cos(angle_rad)
        y = pitch_radius * math.sin(angle_rad)
        pocket = cq.Workplane("XY").transformed(offset=(x, y, 0)).sphere(pocket_radius)
        cage = cage.cut(pocket)
    return cage
