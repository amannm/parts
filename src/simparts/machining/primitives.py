from __future__ import annotations

from typing import Iterable, Literal

import cadquery as cq


Axis = Literal["X", "Y", "Z"]
Plane = Literal["XY", "YZ", "XZ"]
VectorLike = tuple[float, float, float]


def _axis_vector(axis: Axis) -> VectorLike:
    if axis == "X":
        return (1.0, 0.0, 0.0)
    if axis == "Y":
        return (0.0, 1.0, 0.0)
    if axis == "Z":
        return (0.0, 0.0, 1.0)
    raise ValueError(f"Unsupported axis: {axis}")


def _orient_from_z(shape: cq.Workplane, axis: Axis) -> cq.Workplane:
    if axis == "Z":
        return shape
    if axis == "X":
        return shape.rotate((0, 0, 0), (0, 1, 0), 90)
    if axis == "Y":
        return shape.rotate((0, 0, 0), (1, 0, 0), -90)
    raise ValueError(f"Unsupported axis: {axis}")


def box(
    x: float,
    y: float,
    z: float,
    *,
    center: VectorLike = (0.0, 0.0, 0.0),
    centered: tuple[bool, bool, bool] = (True, True, True),
) -> cq.Workplane:
    solid = cq.Workplane("XY").box(x, y, z, centered=centered)
    return solid.translate(center)


def cylinder(
    diameter: float,
    length: float,
    *,
    axis: Axis = "Z",
    center: VectorLike = (0.0, 0.0, 0.0),
    centered: bool = True,
) -> cq.Workplane:
    solid = cq.Workplane("XY").circle(diameter / 2.0).extrude(length, both=centered)
    solid = _orient_from_z(solid, axis)
    return solid.translate(center)


def tube(
    outer_diameter: float,
    inner_diameter: float,
    length: float,
    *,
    axis: Axis = "Z",
    center: VectorLike = (0.0, 0.0, 0.0),
    centered: bool = True,
) -> cq.Workplane:
    if inner_diameter <= 0:
        return cylinder(outer_diameter, length, axis=axis, center=center, centered=centered)
    if outer_diameter <= inner_diameter:
        raise ValueError("Tube outer_diameter must exceed inner_diameter.")
    solid = (
        cq.Workplane("XY")
        .circle(outer_diameter / 2.0)
        .circle(inner_diameter / 2.0)
        .extrude(length, both=centered)
    )
    solid = _orient_from_z(solid, axis)
    return solid.translate(center)


def sphere(
    diameter: float,
    *,
    center: VectorLike = (0.0, 0.0, 0.0),
) -> cq.Workplane:
    return cq.Workplane("XY").sphere(diameter / 2.0).translate(center)


def torus(
    major_radius: float,
    minor_radius: float,
    *,
    axis: Axis = "Z",
    center: VectorLike = (0.0, 0.0, 0.0),
) -> cq.Workplane:
    solid = cq.Workplane("XY").add(cq.Solid.makeTorus(major_radius, minor_radius))
    solid = _orient_from_z(solid, axis)
    return solid.translate(center)


def extruded_profile(
    profile: cq.Workplane,
    distance: float,
    *,
    centered: bool = True,
    twist_angle_deg: float = 0.0,
) -> cq.Workplane:
    if abs(twist_angle_deg) <= 1e-9:
        return profile.extrude(distance, both=centered)
    solid = profile.twistExtrude(distance, twist_angle_deg)
    if centered:
        solid = solid.translate((0.0, 0.0, -distance / 2.0))
    return solid


def swept_profile(
    profile: cq.Workplane,
    path: cq.Workplane,
    *,
    make_solid: bool = True,
    is_frenet: bool = False,
) -> cq.Workplane:
    return profile.sweep(path, makeSolid=make_solid, isFrenet=is_frenet)


def union_all(solids: Iterable[cq.Workplane]) -> cq.Workplane | None:
    result: cq.Workplane | None = None
    for solid in solids:
        result = solid if result is None else result.union(solid)
    return result


def circular_pattern(
    shape: cq.Workplane,
    count: int,
    *,
    axis: Axis = "Z",
    center: VectorLike = (0.0, 0.0, 0.0),
    start_angle_deg: float = 0.0,
    step_angle_deg: float | None = None,
    prefix: str = "instance",
) -> list[tuple[str, cq.Workplane]]:
    if count <= 0:
        return []
    step = step_angle_deg if step_angle_deg is not None else 360.0 / count
    axis_vec = _axis_vector(axis)
    end = tuple(center[i] + axis_vec[i] for i in range(3))
    return [
        (
            f"{prefix}_{idx}",
            shape.rotate(center, end, start_angle_deg + idx * step),
        )
        for idx in range(count)
    ]
