from __future__ import annotations

import math
from dataclasses import dataclass

import cadquery as cq

from features.ball import BallSpec, build_ball
from features.inner_ring import InnerRingSpec, build_inner_ring
from features.outer_ring import OuterRingSpec, build_outer_ring
from features.cage import CageSpec, build_cage
from features.seal import SealSpec, build_seal


@dataclass(frozen=True)
class W61700Spec:
    """SKF W 61700 Deep Groove Ball Bearing specification.

    Default values from SKF datasheet:
    - d = 10 mm (bore diameter)
    - D = 15 mm (outside diameter)
    - B = 3 mm (width)
    - d1 ≈ 11.21 mm (inner ring shoulder diameter)
    - D1 ≈ 13.6 mm (outer ring shoulder diameter)
    - r = 0.15 mm (chamfer)
    """

    bore_diameter: float = 10.0
    outer_diameter: float = 15.0
    width: float = 3.0
    inner_shoulder_diameter: float = 11.21
    outer_shoulder_diameter: float = 13.6
    chamfer: float = 0.15
    ball_diameter: float = 1.5
    num_balls: int = 11
    groove_conformity: float = 1.04
    include_seals: bool = True
    seal_thickness: float = 0.2
    seal_inner_clearance: float = 0.2
    seal_outer_clearance: float = 0.2


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
    if spec.include_seals:
        if spec.seal_thickness <= 0:
            raise ValueError("Seal thickness must be positive.")
        if spec.seal_thickness >= spec.width:
            raise ValueError("Seal thickness must be less than bearing width.")
        if spec.seal_inner_clearance < 0:
            raise ValueError("Seal inner clearance must be non-negative.")
        if spec.seal_outer_clearance < 0:
            raise ValueError("Seal outer clearance must be non-negative.")
        seal_inner_diameter = spec.inner_shoulder_diameter + spec.seal_inner_clearance
        seal_outer_diameter = spec.outer_diameter - spec.seal_outer_clearance
        if seal_inner_diameter <= spec.bore_diameter:
            raise ValueError("Seal inner diameter must be greater than bore diameter.")
        if seal_outer_diameter >= spec.outer_diameter:
            raise ValueError("Seal outer diameter must be less than outer diameter.")
        if seal_inner_diameter >= seal_outer_diameter:
            raise ValueError("Seal inner diameter must be less than seal outer diameter.")


def _groove_depths(
    *,
    inner_outer_radius: float,
    outer_inner_radius: float,
    bore_radius: float,
    outer_radius: float,
    pitch_radius: float,
    groove_radius: float,
    ball_radius: float,
) -> tuple[float, float]:
    # Set groove depths so the ball is tangent to both grooves at the pitch radius.
    inner_depth = inner_outer_radius - pitch_radius + (2.0 * groove_radius) - ball_radius
    outer_depth = pitch_radius - outer_inner_radius + (2.0 * groove_radius) - ball_radius

    inner_wall = inner_outer_radius - bore_radius
    outer_wall = outer_radius - outer_inner_radius

    if inner_depth <= 0:
        raise ValueError("Computed inner groove depth is non-positive; adjust ball size or pitch diameter.")
    if outer_depth <= 0:
        raise ValueError("Computed outer groove depth is non-positive; adjust ball size or pitch diameter.")
    if inner_depth >= inner_wall:
        raise ValueError("Computed inner groove depth exceeds inner ring wall thickness.")
    if outer_depth >= outer_wall:
        raise ValueError("Computed outer groove depth exceeds outer ring wall thickness.")

    return inner_depth, outer_depth


def _seal_specs(spec: W61700Spec) -> tuple[SealSpec, SealSpec]:
    seal_inner_diameter = spec.inner_shoulder_diameter + spec.seal_inner_clearance
    seal_outer_diameter = spec.outer_diameter - spec.seal_outer_clearance
    axial_offset = (spec.width / 2.0) - (spec.seal_thickness / 2.0)
    left = SealSpec(
        inner_diameter=seal_inner_diameter,
        outer_diameter=seal_outer_diameter,
        thickness=spec.seal_thickness,
        axial_offset=-axial_offset,
    )
    right = SealSpec(
        inner_diameter=seal_inner_diameter,
        outer_diameter=seal_outer_diameter,
        thickness=spec.seal_thickness,
        axial_offset=axial_offset,
    )
    return left, right


def build_w61700(spec: W61700Spec = W61700Spec()) -> cq.Assembly:
    _validate_w61700(spec)

    ball_radius = spec.ball_diameter / 2.0
    groove_radius = ball_radius * spec.groove_conformity
    pitch_diameter = (spec.inner_shoulder_diameter + spec.outer_shoulder_diameter) / 2.0
    pitch_radius = pitch_diameter / 2.0

    inner_outer_radius = spec.inner_shoulder_diameter / 2.0
    outer_inner_radius = spec.outer_shoulder_diameter / 2.0
    bore_radius = spec.bore_diameter / 2.0
    outer_radius = spec.outer_diameter / 2.0
    inner_groove_depth, outer_groove_depth = _groove_depths(
        inner_outer_radius=inner_outer_radius,
        outer_inner_radius=outer_inner_radius,
        bore_radius=bore_radius,
        outer_radius=outer_radius,
        pitch_radius=pitch_radius,
        groove_radius=groove_radius,
        ball_radius=ball_radius,
    )

    inner_ring_spec = InnerRingSpec(
        bore_diameter=spec.bore_diameter,
        outer_diameter=spec.inner_shoulder_diameter,
        width=spec.width,
        groove_radius=groove_radius,
        groove_depth=inner_groove_depth,
        chamfer=spec.chamfer,
    )
    inner_ring = build_inner_ring(inner_ring_spec)

    outer_ring_spec = OuterRingSpec(
        inner_diameter=spec.outer_shoulder_diameter,
        outer_diameter=spec.outer_diameter,
        width=spec.width,
        groove_radius=groove_radius,
        groove_depth=outer_groove_depth,
        chamfer=spec.chamfer,
    )
    outer_ring = build_outer_ring(outer_ring_spec)

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

    seal_left = None
    seal_right = None
    if spec.include_seals:
        seal_left_spec, seal_right_spec = _seal_specs(spec)
        seal_left = build_seal(seal_left_spec)
        seal_right = build_seal(seal_right_spec)

    assembly = cq.Assembly()

    assembly.add(
        inner_ring,
        name="inner_ring",
        color=cq.Color(0.7, 0.7, 0.75, 1.0),
    )

    assembly.add(
        outer_ring,
        name="outer_ring",
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

    if spec.include_seals and seal_left and seal_right:
        assembly.add(
            seal_left,
            name="seal_left",
            color=cq.Color(0.1, 0.1, 0.1, 0.9),
        )
        assembly.add(
            seal_right,
            name="seal_right",
            color=cq.Color(0.1, 0.1, 0.1, 0.9),
        )

    return assembly


def build_w61700_components(spec: W61700Spec = W61700Spec()) -> dict:
    _validate_w61700(spec)

    groove_radius = (spec.ball_diameter / 2.0) * spec.groove_conformity
    pitch_diameter = (spec.inner_shoulder_diameter + spec.outer_shoulder_diameter) / 2.0

    inner_outer_radius = spec.inner_shoulder_diameter / 2.0
    outer_inner_radius = spec.outer_shoulder_diameter / 2.0
    bore_radius = spec.bore_diameter / 2.0
    outer_radius = spec.outer_diameter / 2.0
    pitch_radius = pitch_diameter / 2.0
    ball_radius = spec.ball_diameter / 2.0
    inner_groove_depth, outer_groove_depth = _groove_depths(
        inner_outer_radius=inner_outer_radius,
        outer_inner_radius=outer_inner_radius,
        bore_radius=bore_radius,
        outer_radius=outer_radius,
        pitch_radius=pitch_radius,
        groove_radius=groove_radius,
        ball_radius=ball_radius,
    )

    inner_ring_spec = InnerRingSpec(
        bore_diameter=spec.bore_diameter,
        outer_diameter=spec.inner_shoulder_diameter,
        width=spec.width,
        groove_radius=groove_radius,
        groove_depth=inner_groove_depth,
        chamfer=spec.chamfer,
    )

    outer_ring_spec = OuterRingSpec(
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

    seal_specs = None
    if spec.include_seals:
        seal_specs = _seal_specs(spec)

    components = {
        "inner_ring": build_inner_ring(inner_ring_spec),
        "outer_ring": build_outer_ring(outer_ring_spec),
        "ball": build_ball(ball_spec),
        "cage": build_cage(cage_spec),
        "specs": {
            "inner_ring": inner_ring_spec,
            "outer_ring": outer_ring_spec,
            "ball": ball_spec,
            "cage": cage_spec,
            "bearing": spec,
        },
    }
    if spec.include_seals and seal_specs:
        seal_left_spec, seal_right_spec = seal_specs
        components["seal_left"] = build_seal(seal_left_spec)
        components["seal_right"] = build_seal(seal_right_spec)
        components["specs"]["seal_left"] = seal_left_spec
        components["specs"]["seal_right"] = seal_right_spec
    return components


if __name__ == "__main__":
    from cadquery.vis import show

    params = W61700Spec()
    result = build_w61700(params)
    show(result, width=1280, height=720, zoom=0, roll=0, elevation=0, interact=True)
