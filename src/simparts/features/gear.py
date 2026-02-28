from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

import cadquery as cq


@dataclass(frozen=True)
class GearSpec:
    number_of_teeth: int
    module: float
    face_width: float
    pressure_angle_deg: float = 20.0
    helix_angle_deg: float = 0.0
    helix_hand: Literal["RH", "LH"] = "RH"
    profile_shift: float = 0.0
    addendum_coeff: float = 1.0
    dedendum_coeff: float = 1.25
    tooth_thickness: float | None = None
    backlash: float = 0.0
    root_diameter: float | None = None
    outside_diameter: float | None = None
    bore_diameter: float = 0.0
    hub_diameter: float = 0.0
    hub_length: float = 0.0
    chamfer: float = 0.0
    centered: bool = True
    involute_points: int = 12


@dataclass(frozen=True)
class GearGeometry:
    module_normal: float
    module_transverse: float
    pitch_diameter: float
    base_diameter: float
    outside_diameter: float
    root_diameter: float
    addendum: float
    dedendum: float
    clearance: float
    circular_pitch: float
    base_pitch: float
    tooth_thickness: float
    pressure_angle_transverse_deg: float
    pressure_angle_transverse_rad: float
    helix_angle_rad: float
    lead: float | None
    twist_angle_deg: float


def _resolve_module(spec: GearSpec) -> float:
    if spec.module <= 0:
        raise ValueError("Gear module must be positive.")
    return spec.module


def _gear_geometry(spec: GearSpec) -> GearGeometry:
    module_n = _resolve_module(spec)
    if spec.number_of_teeth <= 0:
        raise ValueError("Gear number_of_teeth must be positive.")
    if spec.face_width <= 0:
        raise ValueError("Gear face_width must be positive.")
    if spec.pressure_angle_deg <= 0:
        raise ValueError("Gear pressure_angle_deg must be positive.")
    if abs(spec.helix_angle_deg) >= 89.0:
        raise ValueError("Gear helix_angle_deg must be less than 89 degrees.")
    if spec.addendum_coeff <= 0:
        raise ValueError("Gear addendum_coeff must be positive.")
    if spec.dedendum_coeff <= 0:
        raise ValueError("Gear dedendum_coeff must be positive.")
    if spec.involute_points < 6:
        raise ValueError("Gear involute_points must be at least 6.")
    if spec.backlash < 0:
        raise ValueError("Gear backlash must be non-negative.")
    if spec.bore_diameter < 0:
        raise ValueError("Gear bore_diameter must be non-negative.")
    if spec.hub_diameter < 0:
        raise ValueError("Gear hub_diameter must be non-negative.")
    if spec.hub_length < 0:
        raise ValueError("Gear hub_length must be non-negative.")
    if spec.chamfer < 0:
        raise ValueError("Gear chamfer must be non-negative.")

    beta = math.radians(abs(spec.helix_angle_deg))
    alpha_n = math.radians(spec.pressure_angle_deg)
    alpha_t = math.atan(math.tan(alpha_n) / math.cos(beta)) if beta else alpha_n
    module_t = module_n / math.cos(beta) if beta else module_n

    pitch_diameter = module_t * spec.number_of_teeth
    circular_pitch = math.pi * module_t
    tooth_thickness = (
        spec.tooth_thickness
        if spec.tooth_thickness is not None
        else (circular_pitch / 2.0 + 2.0 * spec.profile_shift * module_n * math.tan(alpha_t))
    )
    tooth_thickness = max(0.0, tooth_thickness - spec.backlash)

    addendum = (spec.addendum_coeff + spec.profile_shift) * module_n
    dedendum = (spec.dedendum_coeff - spec.profile_shift) * module_n
    if dedendum <= 0:
        raise ValueError("Gear dedendum results in non-positive root depth.")

    outside_diameter = spec.outside_diameter
    if outside_diameter is None:
        outside_diameter = pitch_diameter + 2.0 * addendum

    root_diameter = spec.root_diameter
    if root_diameter is None:
        root_diameter = pitch_diameter - 2.0 * dedendum

    if root_diameter <= 0:
        raise ValueError("Gear root_diameter must be positive.")
    if outside_diameter <= root_diameter:
        raise ValueError("Gear outside_diameter must exceed root_diameter.")

    base_diameter = pitch_diameter * math.cos(alpha_t)
    if base_diameter <= 0:
        raise ValueError("Gear base_diameter must be positive.")

    clearance = max(0.0, spec.dedendum_coeff - spec.addendum_coeff) * module_n
    base_pitch = circular_pitch * math.cos(alpha_t)

    lead = None
    twist_angle_deg = 0.0
    if beta:
        lead = math.pi * pitch_diameter / math.tan(beta)
        pitch_radius = pitch_diameter / 2.0
        twist_angle_deg = math.degrees(spec.face_width * math.tan(beta) / pitch_radius)

    if spec.bore_diameter >= root_diameter:
        raise ValueError("Gear bore_diameter must be smaller than root_diameter.")
    if spec.hub_diameter > 0 and spec.hub_diameter < spec.bore_diameter:
        raise ValueError("Gear hub_diameter must be >= bore_diameter.")

    return GearGeometry(
        module_normal=module_n,
        module_transverse=module_t,
        pitch_diameter=pitch_diameter,
        base_diameter=base_diameter,
        outside_diameter=outside_diameter,
        root_diameter=root_diameter,
        addendum=addendum,
        dedendum=dedendum,
        clearance=clearance,
        circular_pitch=circular_pitch,
        base_pitch=base_pitch,
        tooth_thickness=tooth_thickness,
        pressure_angle_transverse_deg=math.degrees(alpha_t),
        pressure_angle_transverse_rad=alpha_t,
        helix_angle_rad=beta,
        lead=lead,
        twist_angle_deg=twist_angle_deg,
    )


def _rotate_point(x: float, y: float, angle_rad: float) -> tuple[float, float]:
    ca = math.cos(angle_rad)
    sa = math.sin(angle_rad)
    return (x * ca - y * sa, x * sa + y * ca)


def _involute_points(
    base_radius: float,
    start_radius: float,
    end_radius: float,
    count: int,
) -> list[tuple[float, float]]:
    if end_radius <= base_radius:
        raise ValueError("Gear outside radius must be larger than base radius.")
    if start_radius < base_radius:
        t_start = 0.0
    else:
        t_start = math.sqrt(start_radius * start_radius - base_radius * base_radius) / base_radius
    t_end = math.sqrt(end_radius * end_radius - base_radius * base_radius) / base_radius
    points: list[tuple[float, float]] = []
    for i in range(count):
        t = t_start + (t_end - t_start) * (i / (count - 1))
        x = base_radius * (math.cos(t) + t * math.sin(t))
        y = base_radius * (math.sin(t) - t * math.cos(t))
        points.append((x, y))
    return points


def _tooth_profile(spec: GearSpec, geom: GearGeometry) -> cq.Workplane:
    pitch_radius = geom.pitch_diameter / 2.0
    base_radius = geom.base_diameter / 2.0
    outside_radius = geom.outside_diameter / 2.0
    root_radius = geom.root_diameter / 2.0

    inv_alpha = math.tan(geom.pressure_angle_transverse_rad) - geom.pressure_angle_transverse_rad
    half_tooth_angle = geom.tooth_thickness / (2.0 * pitch_radius)
    offset = half_tooth_angle - inv_alpha

    involute = _involute_points(
        base_radius,
        root_radius,
        outside_radius,
        spec.involute_points,
    )
    right_flank = [_rotate_point(x, y, offset) for x, y in involute]
    left_flank = [(x, -y) for x, y in right_flank]

    right_base = right_flank[0]
    left_base = left_flank[0]
    right_tip = right_flank[-1]
    left_tip = left_flank[-1]

    angle_right_base = math.atan2(right_base[1], right_base[0])
    right_root = (
        root_radius * math.cos(angle_right_base),
        root_radius * math.sin(angle_right_base),
    )
    left_root = (right_root[0], -right_root[1])

    use_root_segment = root_radius < base_radius - 1e-6

    wp = cq.Workplane("XY")
    if use_root_segment:
        wp = wp.moveTo(right_root[0], right_root[1]).lineTo(right_base[0], right_base[1])
    else:
        wp = wp.moveTo(right_base[0], right_base[1])

    for x, y in right_flank[1:]:
        wp = wp.lineTo(x, y)

    mid_tip = (outside_radius, 0.0)
    wp = wp.threePointArc(mid_tip, left_tip)

    for x, y in reversed(left_flank[:-1]):
        wp = wp.lineTo(x, y)

    if use_root_segment:
        wp = wp.lineTo(left_root[0], left_root[1])

    return wp.close()


def _extrude_tooth(spec: GearSpec, geom: GearGeometry, profile: cq.Workplane) -> cq.Workplane:
    if abs(spec.helix_angle_deg) <= 1e-6:
        return profile.extrude(spec.face_width, both=spec.centered)

    twist_angle = geom.twist_angle_deg
    if spec.helix_angle_deg < 0 or spec.helix_hand.upper() == "LH":
        twist_angle = -abs(twist_angle)

    try:
        tooth = profile.twistExtrude(spec.face_width, twist_angle)
        if spec.centered:
            tooth = tooth.translate((0, 0, -spec.face_width / 2.0))
        return tooth
    except Exception:
        print("WARN: twistExtrude not available; falling back to straight extrude.")
        return profile.extrude(spec.face_width, both=spec.centered)


def build_gear(spec: GearSpec) -> cq.Workplane:
    geom = _gear_geometry(spec)

    root_radius = geom.root_diameter / 2.0
    gear = cq.Workplane("XY").circle(root_radius).extrude(spec.face_width, both=spec.centered)

    profile = _tooth_profile(spec, geom)
    tooth = _extrude_tooth(spec, geom, profile)

    step = 360.0 / spec.number_of_teeth
    for i in range(spec.number_of_teeth):
        gear = gear.union(tooth.rotate((0, 0, 0), (0, 0, 1), i * step))

    if spec.hub_diameter > 0 and spec.hub_length > 0:
        hub = (
            cq.Workplane("XY")
            .circle(spec.hub_diameter / 2.0)
            .extrude(spec.hub_length, both=spec.centered)
        )
        gear = gear.union(hub)

    if spec.bore_diameter > 0:
        bore_length = max(spec.face_width, spec.hub_length)
        bore = (
            cq.Workplane("XY")
            .circle(spec.bore_diameter / 2.0)
            .extrude(bore_length, both=spec.centered)
        )
        gear = gear.cut(bore)

    if spec.chamfer > 0:
        max_chamfer = min(spec.face_width / 4.0, (geom.outside_diameter - geom.root_diameter) / 6.0)
        c = min(spec.chamfer, max_chamfer)
        try:
            gear = gear.faces(">Z or <Z").edges().chamfer(c)
        except Exception:
            print("WARN: Gear chamfer failed (try smaller chamfer).")

    return gear
