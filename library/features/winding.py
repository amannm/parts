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


def _spec_from_params(P) -> WindingSpec:
    w = P.get("winding", {}) or {}
    kind = str(w.get("kind", w.get("type", "hairpin"))).lower()
    varnish_thickness = float(w.get("varnish_thickness", 0.0))
    slot_clearance = float(
        w.get("slot_clearance", w.get("clearance", w.get("liner_thickness", 0.0)))
    )
    if slot_clearance <= 0 and varnish_thickness > 0:
        slot_clearance = varnish_thickness
    return WindingSpec(
        kind=kind,
        slot_clearance=slot_clearance,
        varnish_thickness=varnish_thickness,
        wire_fillet=float(w.get("wire_fillet", 0.0)),
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


def _slot_solid(P, spec: WindingSpec) -> cq.Workplane:
    profile = _slot_profile(P)
    if spec.slot_clearance > 0:
        offset_kind = "intersection" if spec.kind == "hairpin" else "arc"
        try:
            profile = profile.offset2D(-spec.slot_clearance, kind=offset_kind)
        except Exception:
            print("WARN: Winding slot clearance offset failed (try smaller slot_clearance).")
    slot = profile.extrude(_stack_length(P), both=True)
    if spec.kind == "wire" and spec.wire_fillet > 0:
        try:
            bounds = slot.val().BoundingBox()
            max_fillet = min(bounds.xlen, bounds.ylen) * 0.5 * 0.99
            fillet = min(spec.wire_fillet, max_fillet)
            if fillet > 0:
                slot = slot.edges("|Z").fillet(fillet)
        except Exception:
            print("WARN: Winding wire fillet failed (try smaller wire_fillet).")
    return slot


def build_winding_solids(P, spec: WindingSpec | None = None) -> tuple[cq.Workplane | None, cq.Workplane | None]:
    spec = _spec_from_params(P) if spec is None else spec
    _validate_winding(spec)
    g = P["global"]
    Qs = int(g["slots"])
    if Qs <= 0:
        raise ValueError("Global slots must be positive to build windings.")
    slot = _slot_solid(P, spec)
    varnish_slot = None
    if spec.varnish_thickness > 0:
        try:
            varnish_slot = slot.shell(spec.varnish_thickness, kind="intersection")
        except Exception:
            print("WARN: Winding varnish shell failed (try smaller varnish_thickness).")
    copper = None
    varnish = None
    for k in range(Qs):
        ang = 360.0 * k / Qs
        slot_k = slot.rotate((0, 0, 0), (0, 0, 1), ang)
        copper = slot_k if copper is None else copper.union(slot_k)
        if varnish_slot is not None:
            varnish_k = varnish_slot.rotate((0, 0, 0), (0, 0, 1), ang)
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
        assembly.add(varnish, name="windings_varnish", color=varnish_color, material="varnish")
    if copper is not None:
        assembly.add(copper, name="windings_copper", color=copper_color, material="copper")
    return copper, varnish
