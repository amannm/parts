from __future__ import annotations

import math
from dataclasses import dataclass

import cadquery as cq
from cadquery.vis import show

from features.ball import BallSpec, build_ball
from features.inner_race import InnerRaceSpec, build_inner_race
from features.outer_race import OuterRaceSpec, build_outer_race
from features.cage import CageSpec, build_cage


@dataclass(frozen=True)
class W61700Spec:
    """SKF W 61700 Deep Groove Ball Bearing specification.

    Default values from SKF datasheet:
    - d = 10 mm (bore diameter)
    - D = 15 mm (outside diameter)
    - B = 3 mm (width)
    - d1 ≈ 11.21 mm (inner race shoulder diameter)
    - D1 ≈ 13.6 mm (outer race shoulder diameter)
    - r = 0.15 mm (chamfer)
    """

    bore_diameter: float = 10.0
    outer_diameter: float = 15.0
    width: float = 3.0
    inner_shoulder_diameter: float = 11.21
    outer_shoulder_diameter: float = 13.6
    chamfer: float = 0.15
    ball_diameter: float = 1.5
    num_balls: int = 7
    groove_conformity: float = 1.04


def _validate_w61700(spec: W61700Spec) -> None:
    if spec.bore_diameter <= 0:
        raise ValueError("Bore diameter must be positive.")
    if spec.outer_diameter <= spec.bore_diameter:
        raise ValueError("Outer diameter must be greater than bore diameter.")
    if spec.width <= 0:
        raise ValueError("Width must be positive.")
    if spec.inner_shoulder_diameter <= spec.bore_diameter:
        raise ValueError("Inner shoulder diameter must be greater than bore diameter.")
    if spec.outer_shoulder_diameter >= spec.outer_diameter:
        raise ValueError("Outer shoulder diameter must be less than outer diameter.")
    if spec.inner_shoulder_diameter >= spec.outer_shoulder_diameter:
        raise ValueError("Inner shoulder diameter must be less than outer shoulder diameter.")
    if spec.ball_diameter <= 0:
        raise ValueError("Ball diameter must be positive.")
    if spec.num_balls < 3:
        raise ValueError("Number of balls must be at least 3.")
    if spec.groove_conformity < 1.0:
        raise ValueError("Groove conformity must be at least 1.0.")


def build_w61700(spec: W61700Spec = W61700Spec()) -> cq.Assembly:
    _validate_w61700(spec)

    ball_radius = spec.ball_diameter / 2.0
    groove_radius = ball_radius * spec.groove_conformity
    pitch_diameter = (spec.inner_shoulder_diameter + spec.outer_shoulder_diameter) / 2.0
    pitch_radius = pitch_diameter / 2.0

    inner_groove_depth = (spec.inner_shoulder_diameter - spec.bore_diameter) / 2.0 * 0.6
    outer_groove_depth = (spec.outer_diameter - spec.outer_shoulder_diameter) / 2.0 * 0.6

    inner_race_spec = InnerRaceSpec(
        bore_diameter=spec.bore_diameter,
        outer_diameter=spec.inner_shoulder_diameter,
        width=spec.width,
        groove_radius=groove_radius,
        groove_depth=inner_groove_depth,
        chamfer=spec.chamfer,
    )
    inner_race = build_inner_race(inner_race_spec)

    outer_race_spec = OuterRaceSpec(
        inner_diameter=spec.outer_shoulder_diameter,
        outer_diameter=spec.outer_diameter,
        width=spec.width,
        groove_radius=groove_radius,
        groove_depth=outer_groove_depth,
        chamfer=spec.chamfer,
    )
    outer_race = build_outer_race(outer_race_spec)

    ball_spec = BallSpec(diameter=spec.ball_diameter)
    ball = build_ball(ball_spec)

    cage_spec = CageSpec(
        pitch_diameter=pitch_diameter,
        ball_diameter=spec.ball_diameter,
        num_balls=spec.num_balls,
        width=spec.width * 0.7,
        wall_thickness=0.2,
    )
    cage = build_cage(cage_spec)

    assembly = cq.Assembly()

    assembly.add(
        inner_race,
        name="inner_race",
        color=cq.Color(0.7, 0.7, 0.75, 1.0),
    )

    assembly.add(
        outer_race,
        name="outer_race",
        color=cq.Color(0.7, 0.7, 0.75, 1.0),
    )

    angle_step = 360.0 / spec.num_balls
    for i in range(spec.num_balls):
        angle_rad = math.radians(i * angle_step)
        x = pitch_radius * math.cos(angle_rad)
        y = pitch_radius * math.sin(angle_rad)
        assembly.add(
            ball.translate((x, y, 0)),
            name=f"ball_{i}",
            color=cq.Color(0.85, 0.85, 0.88, 1.0),
        )

    assembly.add(
        cage,
        name="cage",
        color=cq.Color(0.85, 0.75, 0.55, 0.8),
    )

    return assembly


def build_w61700_components(spec: W61700Spec = W61700Spec()) -> dict:
    _validate_w61700(spec)

    ball_radius = spec.ball_diameter / 2.0
    groove_radius = ball_radius * spec.groove_conformity
    pitch_diameter = (spec.inner_shoulder_diameter + spec.outer_shoulder_diameter) / 2.0

    inner_groove_depth = (spec.inner_shoulder_diameter - spec.bore_diameter) / 2.0 * 0.6
    outer_groove_depth = (spec.outer_diameter - spec.outer_shoulder_diameter) / 2.0 * 0.6

    inner_race_spec = InnerRaceSpec(
        bore_diameter=spec.bore_diameter,
        outer_diameter=spec.inner_shoulder_diameter,
        width=spec.width,
        groove_radius=groove_radius,
        groove_depth=inner_groove_depth,
        chamfer=spec.chamfer,
    )

    outer_race_spec = OuterRaceSpec(
        inner_diameter=spec.outer_shoulder_diameter,
        outer_diameter=spec.outer_diameter,
        width=spec.width,
        groove_radius=groove_radius,
        groove_depth=outer_groove_depth,
        chamfer=spec.chamfer,
    )

    ball_spec = BallSpec(diameter=spec.ball_diameter)

    cage_spec = CageSpec(
        pitch_diameter=pitch_diameter,
        ball_diameter=spec.ball_diameter,
        num_balls=spec.num_balls,
        width=spec.width * 0.7,
        wall_thickness=0.2,
    )

    return {
        "inner_race": build_inner_race(inner_race_spec),
        "outer_race": build_outer_race(outer_race_spec),
        "ball": build_ball(ball_spec),
        "cage": build_cage(cage_spec),
        "specs": {
            "inner_race": inner_race_spec,
            "outer_race": outer_race_spec,
            "ball": ball_spec,
            "cage": cage_spec,
            "bearing": spec,
        },
    }

if __name__ == "__main__":
    params = W61700Spec()
    result = build_w61700_components(params)
    show(result, width=1280, height=720, zoom=0, roll=0, elevation=0, interact=True)
