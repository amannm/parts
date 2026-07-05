from __future__ import annotations

import math
from dataclasses import dataclass

import cadquery as cq

from simparts.features.screw_thread import (
    ThreadEngagement,
    ThreadProfile,
    ThreadSpec,
    ThreadTaper,
    build_thread_cutter,
)
from simparts.features.utils import validate_non_negative, validate_positive


@dataclass(frozen=True)
class PipeElbowSpec:
    """Female threaded 90-degree elbow.

    The defaults are tuned to the `reference/pipe` fitting, which is labeled as a
    1/2-inch nominal ASME B16.3 Class 150 elbow with an overall envelope close to
    1.76" x 1.70".
    """

    centerline_radius: float = 0.91
    body_outer_diameter: float = 0.96
    bore_diameter: float = 0.62
    horizontal_hub_length: float = 0.32
    vertical_hub_length: float = 0.26
    collar_outer_diameter: float = 1.06
    collar_length: float = 0.10
    port_thread_major_diameter: float = 0.84
    port_thread_tpi: float = 14.0
    port_thread_length: float = 0.47
    port_thread_taper_per_length: float = 1.0 / 16.0


def _validate_pipe_elbow(spec: PipeElbowSpec) -> None:
    validate_positive("Pipe elbow centerline_radius", spec.centerline_radius)
    validate_positive("Pipe elbow body_outer_diameter", spec.body_outer_diameter)
    validate_positive("Pipe elbow bore_diameter", spec.bore_diameter)
    validate_positive("Pipe elbow horizontal_hub_length", spec.horizontal_hub_length)
    validate_positive("Pipe elbow vertical_hub_length", spec.vertical_hub_length)
    validate_positive("Pipe elbow collar_outer_diameter", spec.collar_outer_diameter)
    validate_non_negative("Pipe elbow collar_length", spec.collar_length)
    validate_positive(
        "Pipe elbow port_thread_major_diameter", spec.port_thread_major_diameter
    )
    validate_positive("Pipe elbow port_thread_tpi", spec.port_thread_tpi)
    validate_positive("Pipe elbow port_thread_length", spec.port_thread_length)
    validate_positive(
        "Pipe elbow port_thread_taper_per_length",
        spec.port_thread_taper_per_length,
    )

    body_outer_radius = spec.body_outer_diameter / 2.0
    bore_radius = spec.bore_diameter / 2.0
    collar_outer_radius = spec.collar_outer_diameter / 2.0

    if spec.bore_diameter >= spec.body_outer_diameter:
        raise ValueError("Pipe elbow bore_diameter must be smaller than body_outer_diameter.")
    if spec.port_thread_major_diameter <= spec.bore_diameter:
        raise ValueError(
            "Pipe elbow port_thread_major_diameter must exceed the through bore diameter."
        )
    if spec.port_thread_major_diameter >= spec.body_outer_diameter:
        raise ValueError(
            "Pipe elbow port_thread_major_diameter must stay within the elbow body envelope."
        )
    if spec.collar_outer_diameter < spec.body_outer_diameter:
        raise ValueError(
            "Pipe elbow collar_outer_diameter must be >= body_outer_diameter."
        )
    if spec.collar_length > spec.horizontal_hub_length:
        raise ValueError("Pipe elbow collar_length cannot exceed horizontal_hub_length.")
    if spec.collar_length > spec.vertical_hub_length:
        raise ValueError("Pipe elbow collar_length cannot exceed vertical_hub_length.")
    if spec.centerline_radius <= body_outer_radius:
        raise ValueError(
            "Pipe elbow centerline_radius must exceed the body outer radius."
        )
    if collar_outer_radius <= bore_radius:
        raise ValueError(
            "Pipe elbow collar_outer_diameter must leave wall thickness around the bore."
        )


def _bend_path(radius: float) -> cq.Workplane:
    mid_x = radius * (1.0 - math.sqrt(0.5))
    mid_z = radius * math.sqrt(0.5)
    return (
        cq.Workplane("XZ")
        .moveTo(0.0, 0.0)
        .threePointArc((mid_x, mid_z), (radius, radius))
        .wire()
    )


def _union_all(solids: list[cq.Workplane]) -> cq.Workplane:
    result = solids[0]
    for solid in solids[1:]:
        result = result.union(solid)
    return result


def _build_outer_body(spec: PipeElbowSpec) -> cq.Workplane:
    body_outer_radius = spec.body_outer_diameter / 2.0
    collar_outer_radius = spec.collar_outer_diameter / 2.0
    bend = (
        cq.Workplane("XY")
        .circle(body_outer_radius)
        .sweep(_bend_path(spec.centerline_radius), isFrenet=True)
    )
    vertical_hub = cq.Workplane("XY").circle(body_outer_radius).extrude(
        -spec.vertical_hub_length
    )
    horizontal_hub = (
        cq.Workplane("YZ")
        .circle(body_outer_radius)
        .extrude(spec.horizontal_hub_length)
        .translate((spec.centerline_radius, 0.0, spec.centerline_radius))
    )
    solids = [bend, vertical_hub, horizontal_hub]
    if spec.collar_length > 0:
        vertical_collar = (
            cq.Workplane("XY")
            .circle(collar_outer_radius)
            .extrude(-spec.collar_length)
            .translate((0.0, 0.0, -(spec.vertical_hub_length - spec.collar_length)))
        )
        horizontal_collar = (
            cq.Workplane("YZ")
            .circle(collar_outer_radius)
            .extrude(spec.collar_length)
            .translate(
                (
                    spec.centerline_radius + spec.horizontal_hub_length - spec.collar_length,
                    0.0,
                    spec.centerline_radius,
                )
            )
        )
        solids.extend([vertical_collar, horizontal_collar])
    return _union_all(solids)


def _build_bore(spec: PipeElbowSpec) -> cq.Workplane:
    bore_radius = spec.bore_diameter / 2.0
    bend_bore = (
        cq.Workplane("XY")
        .circle(bore_radius)
        .sweep(_bend_path(spec.centerline_radius), isFrenet=True)
    )
    vertical_bore = cq.Workplane("XY").circle(bore_radius).extrude(-spec.vertical_hub_length)
    horizontal_bore = (
        cq.Workplane("YZ")
        .circle(bore_radius)
        .extrude(spec.horizontal_hub_length)
        .translate((spec.centerline_radius, 0.0, spec.centerline_radius))
    )
    return _union_all([bend_bore, vertical_bore, horizontal_bore])


def _build_port_thread_cutter(spec: PipeElbowSpec) -> cq.Workplane:
    pitch = 1.0 / spec.port_thread_tpi
    sharp_v_height = pitch * math.sqrt(3.0) / 2.0
    thread_profile = ThreadProfile(
        form="NPT",
        included_angle_deg=60.0,
        crest_shape="flat",
        root_shape="flat",
        crest_truncation=sharp_v_height / 8.0,
        root_truncation=sharp_v_height / 4.0,
    )
    thread_spec = ThreadSpec(
        system="NPT",
        side="internal",
        nominal_designation="1/2",
        nominal_diameter=spec.port_thread_major_diameter,
        tpi=spec.port_thread_tpi,
        units="inch",
        profile=thread_profile,
        series="NPT",
        engagement=ThreadEngagement(length=spec.port_thread_length),
        taper=ThreadTaper(
            taper_per_length=spec.port_thread_taper_per_length,
            reference_diameter="major",
            direction="+Z",
        ),
    )
    # Shift so the port face is at z=0 and the thread tapers smaller into negative z.
    return build_thread_cutter(
        thread_spec,
        length=spec.port_thread_length,
        centered=False,
    ).translate((0.0, 0.0, -spec.port_thread_length))


def build_pipe_elbow(spec: PipeElbowSpec = PipeElbowSpec()) -> cq.Workplane:
    _validate_pipe_elbow(spec)

    elbow = _build_outer_body(spec)
    elbow = elbow.cut(_build_bore(spec))

    thread_cutter = _build_port_thread_cutter(spec)
    vertical_thread = thread_cutter.rotate((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), 180.0).translate(
        (0.0, 0.0, -spec.vertical_hub_length)
    )
    horizontal_thread = thread_cutter.rotate(
        (0.0, 0.0, 0.0), (0.0, 1.0, 0.0), 90.0
    ).translate(
        (
            spec.centerline_radius + spec.horizontal_hub_length,
            0.0,
            spec.centerline_radius,
        )
    )
    elbow = elbow.cut(vertical_thread)
    elbow = elbow.cut(horizontal_thread)
    return elbow
