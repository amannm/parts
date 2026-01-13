from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import cadquery as cq


@dataclass(frozen=True)
class WindingSpec:
    kind: Literal["hairpin", "wire"] = "hairpin"
    slot_clearance: float = 0.0
    varnish_thickness: float = 0.0
    wire_fillet: float = 0.0
    radial_count: int = 2
    tangential_count: int = 2
    conductor_gap: float = 0.2
    wire_diameter: float = 0.0
    copper_color: str | tuple[float, float, float, float] | None = None
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


def _validate_winding(spec: WindingSpec) -> None:
    if spec.kind not in ("hairpin", "wire"):
        raise ValueError(f"Unsupported winding kind: {spec.kind}")
    if spec.slot_clearance < 0:
        raise ValueError("Winding slot_clearance must be non-negative.")
    if spec.varnish_thickness < 0:
        raise ValueError("Winding varnish_thickness must be non-negative.")
    if spec.wire_fillet < 0:
        raise ValueError("Winding wire_fillet must be non-negative.")
    if spec.radial_count < 1:
        raise ValueError("Winding radial_count must be at least 1.")
    if spec.tangential_count < 1:
        raise ValueError("Winding tangential_count must be at least 1.")
    if spec.conductor_gap < 0:
        raise ValueError("Winding conductor_gap must be non-negative.")
    if spec.wire_diameter < 0:
        raise ValueError("Winding wire_diameter must be non-negative.")


def _spec_from_params(P) -> WindingSpec:
    w = P.get("winding", {}) or {}
    kind = str(w.get("kind", w.get("type", "hairpin"))).lower()
    varnish_thickness = float(w.get("varnish_thickness", 0.0))
    slot_clearance = float(
        w.get("slot_clearance", w.get("clearance", w.get("liner_thickness", 0.0)))
    )
    if slot_clearance <= 0 and varnish_thickness > 0:
        slot_clearance = varnish_thickness
    if kind == "wire":
        radial_count = int(w.get("wire_radial_count", w.get("radial_count", w.get("rows", 2))))
        tangential_count = int(
            w.get("wire_tangential_count", w.get("tangential_count", w.get("cols", 2)))
        )
        conductor_gap = float(w.get("wire_gap", w.get("conductor_gap", w.get("gap", 0.2))))
        wire_diameter = float(w.get("wire_diameter", 0.0))
    else:
        radial_count = int(w.get("hairpin_radial_count", w.get("radial_count", w.get("rows", 2))))
        tangential_count = int(
            w.get("hairpin_tangential_count", w.get("tangential_count", w.get("cols", 2)))
        )
        conductor_gap = float(w.get("hairpin_gap", w.get("conductor_gap", w.get("gap", 0.2))))
        wire_diameter = 0.0
    return WindingSpec(
        kind=kind,
        slot_clearance=slot_clearance,
        varnish_thickness=varnish_thickness,
        wire_fillet=float(w.get("wire_fillet", 0.0)),
        radial_count=radial_count,
        tangential_count=tangential_count,
        conductor_gap=conductor_gap,
        wire_diameter=wire_diameter,
        copper_color=w.get("copper_color"),
        varnish_color=w.get("varnish_color"),
    )


def _slot_profile(P) -> cq.Workplane:
    s = P["stator"]
    R_si = s["D_si"] / 2
    w0 = s["b_so"] / 2
    w1 = s["b_neck"] / 2
    w2 = s["b_s"] / 2
    x0 = R_si + float(s.get("slot_opening_inset", 0.0))
    x1 = R_si + s["h_tt"]
    x2 = R_si + s["h_s"]
    pts = [
        (x0, +w0),
        (x0, -w0),
        (x1, -w1),
        (x2, -w2),
        (x2, +w2),
        (x1, +w1),
    ]
    return cq.Workplane("XY").polyline(pts).close()


def _stack_length(P) -> float:
    s = P["stator"]
    t = P["build"]["lam_thickness"]
    stack_count = int(s.get("stack_count", 1))
    if stack_count < 1:
        stack_count = 1
    stack_pitch = float(s.get("stack_pitch", 0.0))
    if stack_pitch <= 0:
        varnish_thickness = float(s.get("varnish_thickness", 0.0))
        varnish_pitch = 2.0 * varnish_thickness if varnish_thickness > 0 else 0.0
        stack_pitch = t + varnish_pitch
    return t + (stack_count - 1) * stack_pitch


def _slot_profile_with_clearance(P, spec: WindingSpec) -> cq.Workplane:
    profile = _slot_profile(P)
    if spec.slot_clearance > 0:
        offset_kind = "intersection" if spec.kind == "hairpin" else "arc"
        try:
            profile = profile.offset2D(-spec.slot_clearance, kind=offset_kind)
        except Exception:
            print("WARN: Winding slot clearance offset failed (try smaller slot_clearance).")
    return profile


def _conductor_grid(profile: cq.Workplane, spec: WindingSpec) -> tuple[list[tuple[float, float]], float, float]:
    bounds = profile.val().BoundingBox()
    gap = spec.conductor_gap
    avail_x = bounds.xlen
    avail_y = bounds.ylen
    wire_x = (avail_x - (spec.radial_count - 1) * gap) / spec.radial_count
    wire_y = (avail_y - (spec.tangential_count - 1) * gap) / spec.tangential_count
    if wire_x <= 0 or wire_y <= 0:
        raise ValueError("Winding conductor grid too dense for slot dimensions.")
    x_start = bounds.xmin + wire_x / 2.0
    y_start = bounds.ymin + wire_y / 2.0
    x_step = wire_x + gap
    y_step = wire_y + gap
    centers: list[tuple[float, float]] = []
    for i in range(spec.radial_count):
        x = x_start + i * x_step
        for j in range(spec.tangential_count):
            y = y_start + j * y_step
            centers.append((x, y))
    return centers, wire_x, wire_y


def _build_conductors(P, spec: WindingSpec) -> list[cq.Workplane]:
    profile = _slot_profile_with_clearance(P, spec)
    length = _stack_length(P)
    slot_solid = profile.extrude(length, both=True)
    centers, wire_x, wire_y = _conductor_grid(profile, spec)
    conductors: list[cq.Workplane] = []
    for x, y in centers:
        if spec.kind == "wire":
            diameter = spec.wire_diameter if spec.wire_diameter > 0 else min(wire_x, wire_y)
            diameter = min(diameter, wire_x, wire_y)
            base = cq.Workplane("XY").circle(diameter / 2.0).extrude(length, both=True)
        else:
            base = cq.Workplane("XY").box(wire_x, wire_y, length, centered=(True, True, True))
        base = base.translate((x, y, 0))
        try:
            conductor = base.intersect(slot_solid)
        except Exception:
            print("WARN: Winding conductor intersection failed; using unclipped conductor.")
            conductor = base
        if spec.kind == "hairpin" and spec.wire_fillet > 0:
            try:
                bounds = conductor.val().BoundingBox()
                max_fillet = min(bounds.xlen, bounds.ylen) * 0.5 * 0.99
                fillet = min(spec.wire_fillet, max_fillet)
                if fillet > 0:
                    conductor = conductor.edges("|Z").fillet(fillet)
            except Exception:
                print("WARN: Winding conductor fillet failed (try smaller wire_fillet).")
        conductors.append(conductor)
    return conductors


def build_winding_solids(P, spec: WindingSpec | None = None) -> tuple[cq.Workplane | None, cq.Workplane | None]:
    spec = _spec_from_params(P) if spec is None else spec
    _validate_winding(spec)
    g = P["global"]
    Qs = int(g["slots"])
    if Qs <= 0:
        raise ValueError("Global slots must be positive to build windings.")
    slot_conductors = _build_conductors(P, spec)
    if not slot_conductors:
        return None, None
    varnish_slot = None
    if spec.varnish_thickness > 0:
        varnish_slot = []
        for conductor in slot_conductors:
            try:
                varnish_slot.append(conductor.shell(spec.varnish_thickness, kind="intersection"))
            except Exception:
                print("WARN: Winding varnish shell failed (try smaller varnish_thickness).")
    copper = None
    varnish = None
    for k in range(Qs):
        ang = 360.0 * k / Qs
        for conductor in slot_conductors:
            slot_k = conductor.rotate((0, 0, 0), (0, 0, 1), ang)
            copper = slot_k if copper is None else copper.union(slot_k)
        if varnish_slot:
            for varn in varnish_slot:
                varnish_k = varn.rotate((0, 0, 0), (0, 0, 1), ang)
                varnish = varnish_k if varnish is None else varnish.union(varnish_k)
    return copper, varnish


def add_windings_to_assembly(
    assembly: cq.Assembly,
    P,
    spec: WindingSpec | None = None,
) -> tuple[cq.Workplane | None, cq.Workplane | None]:
    spec = _spec_from_params(P) if spec is None else spec
    _validate_winding(spec)
    copper, varnish = build_winding_solids(P, spec)
    if copper is None and varnish is None:
        return None, None
    copper_color = _color_from(spec.copper_color, (0.72, 0.45, 0.2, 1.0))
    varnish_color = _color_from(spec.varnish_color, (0.98, 0.72, 0.2, 0.25))
    if varnish is not None:
        assembly.add(varnish, name="windings_varnish", color=varnish_color)
    if copper is not None:
        assembly.add(copper, name="windings_copper", color=copper_color)
    return copper, varnish
