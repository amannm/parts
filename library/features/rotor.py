from __future__ import annotations

from dataclasses import dataclass

import cadquery as cq

from features.magnet import MagnetSpec, magnet_pockets_and_solids_for_pole


@dataclass(frozen=True)
class RotorSpec:
    poles: int
    lam_thickness: float
    outer_diameter: float
    shaft_diameter: float
    angle_offset_deg: float = 0.0
    varnish_thickness: float = 0.0
    stack_count: int = 1
    stack_pitch: float = 0.0
    steel_color: str | tuple[float, float, float, float] | None = None
    varnish_color: str | tuple[float, float, float, float] | None = None


def _color_from(value, fallback):
    if value is None:
        value = fallback
    if isinstance(value, str):
        return cq.Color(value)
    if isinstance(value, (list, tuple)):
        if len(value) == 3:
            return cq.Color(*value)
        if len(value) == 4:
            return cq.Color(*value)
    return cq.Color(*fallback)


def _validate_positive(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be positive.")


def _validate_non_negative(name: str, value: float) -> None:
    if value < 0:
        raise ValueError(f"{name} must be non-negative.")


def _validate_spec(spec: RotorSpec) -> None:
    if spec.poles <= 0:
        raise ValueError("Rotor poles must be positive.")
    _validate_positive("Rotor lam_thickness", spec.lam_thickness)
    _validate_positive("Rotor outer_diameter", spec.outer_diameter)
    _validate_positive("Rotor shaft_diameter", spec.shaft_diameter)
    if spec.shaft_diameter >= spec.outer_diameter:
        raise ValueError("Rotor outer_diameter must exceed shaft_diameter.")
    if spec.stack_count < 1:
        raise ValueError("Rotor stack_count must be at least 1.")
    _validate_non_negative("Rotor stack_pitch", spec.stack_pitch)
    _validate_non_negative("Rotor varnish_thickness", spec.varnish_thickness)


def make_rotor_and_magnets(
    spec: RotorSpec,
    magnet_spec: MagnetSpec,
    *,
    include_magnets: bool = False,
):
    if spec is None:
        raise ValueError("Rotor spec is required to build rotor and magnets.")
    if magnet_spec is None:
        raise ValueError("Magnet spec is required to build rotor and magnets.")
    _validate_spec(spec)
    t = spec.lam_thickness
    varnish_thickness = float(spec.varnish_thickness)
    stack_count = int(spec.stack_count)
    if stack_count < 1:
        stack_count = 1
    stack_pitch = float(spec.stack_pitch)
    if stack_pitch <= 0:
        varnish_pitch = 2.0 * varnish_thickness if varnish_thickness > 0 else 0.0
        stack_pitch = t + varnish_pitch
    magnet_length = t + (stack_count - 1) * stack_pitch
    poles = int(spec.poles)
    pole_pitch = 360.0 / float(poles)
    offset = float(spec.angle_offset_deg)
    R_ro = float(spec.outer_diameter) / 2.0
    R_sh = float(spec.shaft_diameter) / 2.0
    rotor = cq.Workplane("XY").circle(R_ro).circle(R_sh).extrude(t, both=True)
    pocket_cutters = None
    magnet_solids = None
    for i in range(poles):
        pole_center = offset + i * pole_pitch
        pole_pockets, pole_magnets = magnet_pockets_and_solids_for_pole(
            magnet_spec,
            pole_center,
            t,
            magnet_length,
            include_magnets=include_magnets,
        )
        pocket_cutters = pole_pockets if pocket_cutters is None else pocket_cutters.union(pole_pockets)
        if pole_magnets is not None:
            magnet_solids = pole_magnets if magnet_solids is None else magnet_solids.union(pole_magnets)
    if pocket_cutters is not None:
        rotor = rotor.cut(pocket_cutters)

    varnish = None
    if varnish_thickness > 0:
        try:
            varnish = rotor.shell(varnish_thickness, kind="intersection")
        except Exception:
            print("WARN: Rotor varnish shell failed (try smaller varnish_thickness).")

    assembly = cq.Assembly()
    steel_color = _color_from(spec.steel_color, (0.25, 0.25, 0.25, 1.0))
    varnish_color = _color_from(spec.varnish_color, (0.98, 0.72, 0.2, 0.25))
    z0 = -0.5 * (stack_count - 1) * stack_pitch
    for idx in range(stack_count):
        z = z0 + idx * stack_pitch
        if varnish is not None:
            assembly.add(
                varnish.translate((0, 0, z)),
                name=f"rotor_varnish_{idx}",
                color=varnish_color,
            )
        assembly.add(
            rotor.translate((0, 0, z)),
            name=f"rotor_steel_{idx}",
            color=steel_color,
        )

    return assembly, rotor, varnish, magnet_solids
