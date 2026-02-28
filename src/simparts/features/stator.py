from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import cadquery as cq

from simparts.features.utils import color_from, validate_non_negative, validate_positive


@dataclass(frozen=True)
class StatorSpec:
    slots: int
    lam_thickness: float
    inner_diameter: float
    outer_diameter: float | None = None
    yoke_thickness: float | None = None
    slot_style: Literal["open", "semi_closed", "closed"] = "semi_closed"
    slot_opening_inset: float = 0.0
    slot_opening_depth: float = 0.0
    slot_neck_height: float = 0.0
    slot_body_height: float = 0.0
    slot_depth: float | None = None
    slot_opening_width: float | None = None
    slot_opening_angle_deg: float | None = None
    slot_neck_width: float | None = None
    slot_body_top_width: float | None = None
    slot_body_bottom_width: float | None = None
    slot_pitch_margin: float = 0.98
    slot_angle_offset_deg: float = 0.0
    slot_bottom_arc_radius: float = 0.0
    slot_corner_radius: float = 0.0
    slot_mouth_radius: float = 0.0
    tooth_root_radius: float = 0.0
    slot_bottom_radius: float = 0.0
    segment_count: int = 1
    segment_gap: float = 0.0
    segment_gap_deg: float = 0.0
    segment_offset_deg: float = 0.0
    segment_radial_margin: float = 0.1
    stack_count: int = 1
    stack_pitch: float = 0.0
    varnish_thickness: float = 0.0
    fillet_enabled: bool = False
    fillet_r: float = 0.0
    steel_color: str | tuple[float, float, float, float] | None = None
    varnish_color: str | tuple[float, float, float, float] | None = None


def _validate_spec(spec: StatorSpec) -> None:
    if spec.slots <= 0:
        raise ValueError("Stator slots must be positive.")
    validate_positive("Stator lam_thickness", spec.lam_thickness)
    validate_positive("Stator inner_diameter", spec.inner_diameter)
    if spec.outer_diameter is not None:
        validate_positive("Stator outer_diameter", spec.outer_diameter)
    if spec.yoke_thickness is not None:
        validate_positive("Stator yoke_thickness", spec.yoke_thickness)
    if spec.slot_style not in ("open", "semi_closed", "closed"):
        raise ValueError(f"Unsupported slot_style: {spec.slot_style}")
    validate_non_negative("Slot opening inset", spec.slot_opening_inset)
    validate_non_negative("Slot opening depth", spec.slot_opening_depth)
    validate_non_negative("Slot neck height", spec.slot_neck_height)
    validate_non_negative("Slot body height", spec.slot_body_height)
    if spec.slot_depth is not None:
        validate_non_negative("Slot depth", spec.slot_depth)
    if spec.slot_opening_width is not None:
        validate_non_negative("Slot opening width", spec.slot_opening_width)
    if spec.slot_opening_angle_deg is not None:
        validate_non_negative("Slot opening angle", spec.slot_opening_angle_deg)
    validate_non_negative("Slot pitch margin", spec.slot_pitch_margin)
    validate_non_negative("Slot bottom arc radius", spec.slot_bottom_arc_radius)
    validate_non_negative("Slot corner radius", spec.slot_corner_radius)
    validate_non_negative("Slot mouth radius", spec.slot_mouth_radius)
    validate_non_negative("Tooth root radius", spec.tooth_root_radius)
    validate_non_negative("Slot bottom radius", spec.slot_bottom_radius)
    if spec.segment_count < 1:
        raise ValueError("segment_count must be at least 1.")
    validate_non_negative("Segment gap", spec.segment_gap)
    validate_non_negative("Segment gap deg", spec.segment_gap_deg)
    validate_non_negative("Segment radial margin", spec.segment_radial_margin)
    if spec.stack_count < 1:
        raise ValueError("stack_count must be at least 1.")
    validate_non_negative("Stack pitch", spec.stack_pitch)
    validate_non_negative("Varnish thickness", spec.varnish_thickness)
    validate_non_negative("Stator fillet radius", spec.fillet_r)


def _stator_geometry(spec: StatorSpec) -> dict:
    _validate_spec(spec)
    Qs = int(spec.slots)
    R_si = spec.inner_diameter / 2.0

    slot_style = spec.slot_style
    opening_inset = spec.slot_opening_inset
    if slot_style == "open":
        opening_inset = 0.0
    if slot_style == "closed" and opening_inset <= 0:
        raise ValueError("Closed slots require bridge_thickness / slot_opening_inset > 0.")

    h_so = spec.slot_opening_depth
    h_sn = spec.slot_neck_height
    h_sb = spec.slot_body_height
    if h_sb <= 0:
        if spec.slot_depth is None:
            raise ValueError("Slot body height (slot_body_height) or slot_depth is required.")
        h_sb = spec.slot_depth - h_so - h_sn
    validate_positive("Slot body height", h_sb)
    slot_depth = h_so + h_sn + h_sb

    b_so = spec.slot_opening_width
    if b_so is None or b_so <= 0:
        alpha = spec.slot_opening_angle_deg
        if alpha is None or alpha <= 0:
            raise ValueError("Slot opening width (slot_opening_width) or angle is required.")
        b_so = 2.0 * (R_si + opening_inset) * math.sin(math.radians(alpha) / 2.0)
    b_sn = spec.slot_neck_width if spec.slot_neck_width is not None else b_so
    b_sb1 = spec.slot_body_top_width if spec.slot_body_top_width is not None else b_sn
    b_sb2 = spec.slot_body_bottom_width if spec.slot_body_bottom_width is not None else b_sb1
    validate_positive("Slot opening width", b_so)
    validate_positive("Slot neck width", b_sn)
    validate_positive("Slot body top width", b_sb1)
    validate_positive("Slot body bottom width", b_sb2)

    if spec.outer_diameter is None:
        if spec.yoke_thickness is None:
            raise ValueError("Stator outer_diameter or yoke_thickness is required.")
        R_so = R_si + opening_inset + slot_depth + spec.yoke_thickness
    else:
        R_so = spec.outer_diameter / 2.0

    if R_so <= R_si:
        raise ValueError("Stator outer_diameter must be larger than inner_diameter.")
    if R_si + opening_inset + slot_depth >= R_so:
        raise ValueError("Slot depth exceeds available stator radial thickness.")

    x0 = R_si + opening_inset
    x1 = x0 + h_so
    x2 = x1 + h_sn
    x3 = x2 + h_sb

    bottom_arc_radius = spec.slot_bottom_arc_radius
    x3_tan = x3
    if bottom_arc_radius > 0:
        if bottom_arc_radius < b_sb2 / 2.0:
            raise ValueError("slot_bottom_arc_radius must be >= slot bottom half-width.")
        sagitta = bottom_arc_radius - math.sqrt(bottom_arc_radius**2 - (b_sb2 / 2.0) ** 2)
        x3_tan = x3 - sagitta
        if x3_tan <= x2:
            raise ValueError("slot_bottom_arc_radius too large for slot body height.")

    slot_pitch_margin = spec.slot_pitch_margin
    if not 0.1 <= slot_pitch_margin <= 1.0:
        raise ValueError("slot_pitch_margin must be between 0.1 and 1.0.")

    def _check_width(width: float, radius: float, label: str) -> None:
        pitch = 2.0 * math.pi * radius / Qs
        if width >= pitch * slot_pitch_margin:
            raise ValueError(f"{label} exceeds slot pitch at radius {radius:.3f}.")

    _check_width(b_so, x0, "Slot opening width")
    _check_width(b_sn, x1, "Slot neck width")
    _check_width(b_sb1, x2, "Slot body top width")
    _check_width(b_sb2, x3_tan, "Slot body bottom width")

    segment_count = spec.segment_count if spec.segment_count > 0 else 1
    segment_gap = spec.segment_gap
    if segment_gap <= 0 and spec.segment_gap_deg > 0:
        segment_gap = math.radians(spec.segment_gap_deg) * (R_si + R_so) * 0.5

    return {
        "Qs": Qs,
        "R_si": R_si,
        "R_so": R_so,
        "slot_style": slot_style,
        "opening_inset": opening_inset,
        "slot_depth": slot_depth,
        "x0": x0,
        "x1": x1,
        "x2": x2,
        "x3": x3,
        "x3_tan": x3_tan,
        "w0": b_so / 2.0,
        "w1": b_sn / 2.0,
        "w2": b_sb1 / 2.0,
        "w3": b_sb2 / 2.0,
        "slot_angle_offset": spec.slot_angle_offset_deg,
        "segment_count": segment_count,
        "segment_gap": segment_gap,
        "segment_offset": spec.segment_offset_deg,
        "bottom_arc_radius": bottom_arc_radius,
    }


def _dedupe_points(points, tol: float = 1e-9):
    cleaned = []
    for x, y in points:
        if not cleaned:
            cleaned.append((x, y))
            continue
        px, py = cleaned[-1]
        if abs(x - px) > tol or abs(y - py) > tol:
            cleaned.append((x, y))
    return cleaned


def _slot_profile_from_geom(geom: dict) -> cq.Workplane:
    neg_pts = _dedupe_points(
        [
            (geom["x0"], +geom["w0"]),
            (geom["x0"], -geom["w0"]),
            (geom["x1"], -geom["w1"]),
            (geom["x2"], -geom["w2"]),
            (geom["x3_tan"], -geom["w3"]),
        ]
    )
    if len(neg_pts) < 2:
        raise ValueError("Slot profile collapsed; check slot dimensions.")
    wp = cq.Workplane("XY").moveTo(*neg_pts[0])
    for x, y in neg_pts[1:]:
        wp = wp.lineTo(x, y)
    if geom["bottom_arc_radius"] > 0:
        wp = wp.threePointArc((geom["x3"], 0.0), (geom["x3_tan"], +geom["w3"]))
    else:
        wp = wp.lineTo(geom["x3_tan"], +geom["w3"])
    pos_pts = _dedupe_points(
        [
            (geom["x3_tan"], +geom["w3"]),
            (geom["x2"], +geom["w2"]),
            (geom["x1"], +geom["w1"]),
            (geom["x0"], +geom["w0"]),
        ]
    )
    for x, y in pos_pts[1:]:
        wp = wp.lineTo(x, y)
    return wp.close()


def build_slot_profile(spec: StatorSpec) -> cq.Workplane:
    geom = _stator_geometry(spec)
    return _slot_profile_from_geom(geom)


def _edges_at_points(solid, points, tol: float):
    points = list(points)

    def _matches(edge) -> bool:
        bb = edge.BoundingBox()
        cx = 0.5 * (bb.xmin + bb.xmax)
        cy = 0.5 * (bb.ymin + bb.ymax)
        for px, py in points:
            dx = cx - px
            dy = cy - py
            if dx * dx + dy * dy <= tol * tol:
                return True
        return False

    return solid.edges("|Z").filter(_matches)


def _apply_corner_fillet(
    solid,
    points,
    radius: float,
    label: str,
    tol: float,
):
    if radius <= 0:
        return solid
    try:
        edges = _edges_at_points(solid, points, tol)
        if edges.size() == 0:
            print(f"WARN: {label} fillet skipped (no matching edges).")
            return solid
        return edges.fillet(radius)
    except Exception:
        print(f"WARN: {label} fillet failed (try smaller radius).")
        return solid


def build_slot_cutter(spec: StatorSpec):
    geom = _stator_geometry(spec)
    slot = _slot_profile_from_geom(geom).extrude(spec.lam_thickness, both=True)
    corner_default = spec.slot_corner_radius
    r_mouth = spec.slot_mouth_radius
    r_root = spec.tooth_root_radius
    r_bottom = spec.slot_bottom_radius
    if corner_default > 0:
        if r_mouth <= 0:
            r_mouth = corner_default
        if r_root <= 0:
            r_root = corner_default
        if r_bottom <= 0:
            r_bottom = corner_default
    if geom["bottom_arc_radius"] > 0:
        r_bottom = 0.0
    tol = max(1e-3, 0.25 * max(r_mouth, r_root, r_bottom, corner_default))
    if r_mouth > 0:
        slot = _apply_corner_fillet(
            slot,
            [(geom["x0"], geom["w0"]), (geom["x0"], -geom["w0"])],
            r_mouth,
            "Slot mouth",
            tol,
        )
    if r_root > 0:
        slot = _apply_corner_fillet(
            slot,
            [(geom["x2"], geom["w2"]), (geom["x2"], -geom["w2"])],
            r_root,
            "Tooth root",
            tol,
        )
    if r_bottom > 0:
        slot = _apply_corner_fillet(
            slot,
            [(geom["x3_tan"], geom["w3"]), (geom["x3_tan"], -geom["w3"])],
            r_bottom,
            "Slot bottom",
            tol,
        )
    return slot


def build_stator(
    spec: StatorSpec,
    winding_spec=None,
):
    geom = _stator_geometry(spec)
    R_so = geom["R_so"]
    R_si = geom["R_si"]
    stator = (
        cq.Workplane("XY")
        .circle(R_so)
        .circle(R_si)
        .extrude(spec.lam_thickness, both=True)
    )
    slot_cutter = build_slot_cutter(spec)
    for k in range(geom["Qs"]):
        ang = geom["slot_angle_offset"] + 360.0 * k / geom["Qs"]
        c = slot_cutter.rotate((0, 0, 0), (0, 0, 1), ang)
        stator = stator.cut(c)
    if geom["segment_count"] > 1 and geom["segment_gap"] > 0:
        radial_len = (R_so - R_si) + spec.segment_radial_margin * 2.0
        gap = cq.Workplane("XY").rect(radial_len, geom["segment_gap"]).extrude(spec.lam_thickness, both=True)
        gap = gap.translate(((R_so + R_si) * 0.5, 0, 0))
        gap_cutter = None
        for k in range(geom["segment_count"]):
            ang = geom["segment_offset"] + 360.0 * k / geom["segment_count"]
            cutter = gap.rotate((0, 0, 0), (0, 0, 1), ang)
            gap_cutter = cutter if gap_cutter is None else gap_cutter.union(cutter)
        stator = stator.cut(gap_cutter)
    stator_core = stator
    if spec.fillet_enabled and spec.fillet_r > 0:
        try:
            stator = stator.edges("|Z").fillet(spec.fillet_r)
        except Exception:
            print("WARN: Stator fillet failed (try smaller fillet_r).")
    varnish = None
    varnish_thickness = spec.varnish_thickness
    if varnish_thickness > 0:
        for candidate in (stator, stator_core):
            try:
                varnish = candidate.shell(varnish_thickness, kind="intersection")
                break
            except Exception:
                varnish = None
        if varnish is None:
            print("WARN: Stator varnish shell failed (try smaller varnish_thickness).")
    stack_count = max(1, int(spec.stack_count))
    stack_pitch = spec.stack_pitch
    if stack_pitch <= 0:
        steel_thickness = stator.val().BoundingBox().zlen
        varnish_pitch = 2.0 * varnish_thickness
        stack_pitch = steel_thickness + varnish_pitch
    assembly = cq.Assembly()
    steel_color = color_from(spec.steel_color, (0.25, 0.25, 0.25, 1.0))
    varnish_color = color_from(spec.varnish_color, (0.98, 0.72, 0.2, 0.25))
    z0 = -0.5 * (stack_count - 1) * stack_pitch
    for idx in range(stack_count):
        z = z0 + idx * stack_pitch
        if varnish is not None:
            assembly.add(
                varnish.translate((0, 0, z)),
                name=f"stator_varnish_{idx}",
                color=varnish_color,
            )
        assembly.add(
            stator.translate((0, 0, z)),
            name=f"stator_steel_{idx}",
            color=steel_color,
        )
    if winding_spec is not None:
        from simparts.features.winding import add_windings_to_assembly

        add_windings_to_assembly(assembly, spec, winding_spec)

    return assembly, stator, varnish
