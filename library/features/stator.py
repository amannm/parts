from __future__ import annotations

import math

import cadquery as cq


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


def _float_from(mapping, *keys, default=None):
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return float(mapping[key])
    if default is None:
        return None
    return float(default)


def _validate_positive(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be positive.")


def _validate_non_negative(name: str, value: float) -> None:
    if value < 0:
        raise ValueError(f"{name} must be non-negative.")


def _stator_geometry(P) -> dict:
    g = P["global"]
    s = P["stator"]
    Qs = int(g["slots"])
    if Qs <= 0:
        raise ValueError("Global slots must be positive to build a stator.")
    D_si = _float_from(s, "D_si", "stator_inner_diameter")
    if D_si is None:
        raise ValueError("Stator D_si (inner diameter) is required.")
    _validate_positive("Stator D_si", D_si)
    R_si = D_si / 2.0

    slot_style = str(s.get("slot_style", s.get("slot_type", "semi_closed"))).lower()
    if slot_style not in ("open", "semi_closed", "closed"):
        raise ValueError(f"Unsupported slot_style: {slot_style}")

    opening_inset = _float_from(
        s,
        "slot_opening_inset",
        "bridge_thickness",
        "t_br",
        default=0.0,
    )
    _validate_non_negative("Slot opening inset", opening_inset)
    if slot_style == "open":
        opening_inset = 0.0
    if slot_style == "closed" and opening_inset <= 0:
        raise ValueError("Closed slots require bridge_thickness / slot_opening_inset > 0.")

    h_so = _float_from(s, "h_so", "slot_opening_depth", default=_float_from(s, "h_tt", default=0.0))
    h_sn = _float_from(s, "h_sn", "slot_neck_height", default=0.0)
    h_sb = _float_from(s, "h_sb", "slot_body_height")
    if h_sb is None:
        h_s_total = _float_from(s, "h_s", "slot_depth")
        if h_s_total is None:
            raise ValueError("Slot body height (h_sb) or slot depth (h_s) is required.")
        h_sb = h_s_total - h_so - h_sn
    _validate_non_negative("Slot opening depth", h_so)
    _validate_non_negative("Slot neck height", h_sn)
    _validate_positive("Slot body height", h_sb)
    slot_depth = h_so + h_sn + h_sb

    b_so = _float_from(s, "b_so", "slot_opening_width")
    if b_so is None or b_so <= 0:
        alpha = _float_from(s, "alpha_so_deg", "slot_opening_angle_deg")
        if alpha is None or alpha <= 0:
            raise ValueError("Slot opening width (b_so) or angle (alpha_so_deg) is required.")
        b_so = 2.0 * (R_si + opening_inset) * math.sin(math.radians(alpha) / 2.0)
    b_sn = _float_from(s, "b_sn", "slot_neck_width", default=_float_from(s, "b_neck", default=b_so))
    b_sb1 = _float_from(
        s,
        "b_sb1",
        "slot_body_width_top",
        default=_float_from(s, "b_s", default=b_sn),
    )
    b_sb2 = _float_from(
        s,
        "b_sb2",
        "slot_body_width_bottom",
        default=_float_from(s, "b_s", default=b_sb1),
    )
    _validate_positive("Slot opening width", b_so)
    _validate_positive("Slot neck width", b_sn)
    _validate_positive("Slot body top width", b_sb1)
    _validate_positive("Slot body bottom width", b_sb2)

    D_so = _float_from(s, "D_so", "stator_outer_diameter")
    if D_so is None:
        yoke_thickness = _float_from(s, "t_y", "yoke_thickness")
        if yoke_thickness is None:
            raise ValueError("Stator D_so (outer diameter) or yoke_thickness is required.")
        _validate_positive("Stator yoke thickness", yoke_thickness)
        R_so = R_si + opening_inset + slot_depth + yoke_thickness
    else:
        _validate_positive("Stator D_so", D_so)
        R_so = D_so / 2.0

    if R_so <= R_si:
        raise ValueError("Stator D_so must be larger than D_si.")
    if R_si + opening_inset + slot_depth >= R_so:
        raise ValueError("Slot depth exceeds available stator radial thickness.")

    slot_pitch_margin = float(s.get("slot_pitch_margin", 0.98))
    if not 0.1 <= slot_pitch_margin <= 1.0:
        raise ValueError("slot_pitch_margin must be between 0.1 and 1.0.")

    def _check_width(width: float, radius: float, label: str) -> None:
        pitch = 2.0 * math.pi * radius / Qs
        if width >= pitch * slot_pitch_margin:
            raise ValueError(f"{label} exceeds slot pitch at radius {radius:.3f}.")

    _check_width(b_so, R_si + opening_inset, "Slot opening width")
    _check_width(b_sn, R_si + opening_inset + h_so, "Slot neck width")
    _check_width(b_sb1, R_si + opening_inset + h_so + h_sn, "Slot body top width")
    _check_width(b_sb2, R_si + opening_inset + slot_depth, "Slot body bottom width")

    slot_angle_offset = float(s.get("slot_angle_offset_deg", g.get("angle_offset_deg", 0.0)))

    segment_count = int(s.get("segment_count", s.get("N_seg", 1)))
    if segment_count < 1:
        segment_count = 1
    segment_gap = _float_from(s, "segment_gap", "g_seg", default=0.0)
    if segment_gap <= 0:
        gap_deg = _float_from(s, "segment_gap_deg", default=0.0)
        if gap_deg > 0:
            segment_gap = math.radians(gap_deg) * (R_si + R_so) * 0.5
    segment_offset = float(s.get("segment_offset_deg", 0.0))

    return {
        "Qs": Qs,
        "R_si": R_si,
        "R_so": R_so,
        "slot_style": slot_style,
        "opening_inset": opening_inset,
        "slot_depth": slot_depth,
        "x0": R_si + opening_inset,
        "x1": R_si + opening_inset + h_so,
        "x2": R_si + opening_inset + h_so + h_sn,
        "x3": R_si + opening_inset + slot_depth,
        "w0": b_so / 2.0,
        "w1": b_sn / 2.0,
        "w2": b_sb1 / 2.0,
        "w3": b_sb2 / 2.0,
        "slot_angle_offset": slot_angle_offset,
        "segment_count": segment_count,
        "segment_gap": segment_gap,
        "segment_offset": segment_offset,
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
    pts = [
        (geom["x0"], +geom["w0"]),
        (geom["x0"], -geom["w0"]),
        (geom["x1"], -geom["w1"]),
        (geom["x2"], -geom["w2"]),
        (geom["x3"], -geom["w3"]),
        (geom["x3"], +geom["w3"]),
        (geom["x2"], +geom["w2"]),
        (geom["x1"], +geom["w1"]),
    ]
    pts = _dedupe_points(pts)
    if len(pts) < 3:
        raise ValueError("Slot profile collapsed; check slot dimensions.")
    return cq.Workplane("XY").polyline(pts).close()


def build_slot_profile(P) -> cq.Workplane:
    geom = _stator_geometry(P)
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


def make_slot_cutter(P):
    s = P["stator"]
    t = P["build"]["lam_thickness"]
    geom = _stator_geometry(P)
    slot = _slot_profile_from_geom(geom).extrude(t, both=True)
    corner_default = _float_from(s, "slot_corner_radius", default=0.0)
    r_mouth = _float_from(s, "r_so_f", "slot_mouth_radius", "slot_opening_fillet", default=0.0)
    r_root = _float_from(s, "r_tr", "tooth_root_radius", "tooth_root_fillet", default=0.0)
    r_bottom = _float_from(s, "r_sb_f", "slot_bottom_radius", "slot_bottom_fillet", default=0.0)
    if corner_default > 0:
        if r_mouth <= 0:
            r_mouth = corner_default
        if r_root <= 0:
            r_root = corner_default
        if r_bottom <= 0:
            r_bottom = corner_default
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
            [(geom["x3"], geom["w3"]), (geom["x3"], -geom["w3"])],
            r_bottom,
            "Slot bottom",
            tol,
        )
    return slot


def make_stator(P):
    g = P["global"]
    s = P["stator"]
    t = P["build"]["lam_thickness"]
    geom = _stator_geometry(P)
    R_so = geom["R_so"]
    R_si = geom["R_si"]
    stator = (
        cq.Workplane("XY")
        .circle(R_so)
        .circle(R_si)
        .extrude(t, both=True)
    )
    slot_cutter = make_slot_cutter(P)
    for k in range(geom["Qs"]):
        ang = geom["slot_angle_offset"] + 360.0 * k / geom["Qs"]
        c = slot_cutter.rotate((0, 0, 0), (0, 0, 1), ang)
        stator = stator.cut(c)
    if geom["segment_count"] > 1 and geom["segment_gap"] > 0:
        radial_len = (R_so - R_si) + float(s.get("segment_radial_margin", 0.1)) * 2.0
        gap = cq.Workplane("XY").rect(radial_len, geom["segment_gap"]).extrude(t, both=True)
        gap = gap.translate(((R_so + R_si) * 0.5, 0, 0))
        gap_cutter = None
        for k in range(geom["segment_count"]):
            ang = geom["segment_offset"] + 360.0 * k / geom["segment_count"]
            cutter = gap.rotate((0, 0, 0), (0, 0, 1), ang)
            gap_cutter = cutter if gap_cutter is None else gap_cutter.union(cutter)
        stator = stator.cut(gap_cutter)
    stator_core = stator
    if s.get("fillet_enabled", False) and s.get("fillet_r", 0) > 0:
        try:
            stator = stator.edges("|Z").fillet(s["fillet_r"])
        except Exception:
            print("WARN: Stator fillet failed (try smaller fillet_r).")
    varnish = None
    varnish_thickness = float(s.get("varnish_thickness", 0.0))
    if varnish_thickness > 0:
        for candidate in (stator, stator_core):
            try:
                varnish = candidate.shell(varnish_thickness, kind="intersection")
                break
            except Exception:
                varnish = None
        if varnish is None:
            print("WARN: Stator varnish shell failed (try smaller varnish_thickness).")
    stack_count = int(s.get("stack_count", 1))
    if stack_count < 1:
        stack_count = 1
    stack_pitch = float(s.get("stack_pitch", 0.0))
    if stack_pitch <= 0:
        steel_thickness = stator.val().BoundingBox().zlen
        varnish_pitch = 2.0 * varnish_thickness
        stack_pitch = steel_thickness + varnish_pitch
    assembly = cq.Assembly()
    steel_color = _color_from(s.get("steel_color"), (0.25, 0.25, 0.25, 1.0))
    varnish_color = _color_from(s.get("varnish_color"), (0.98, 0.72, 0.2, 0.25))
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
    winding_cfg = P.get("winding", None)
    if winding_cfg is not None and winding_cfg.get("enabled", True):
        from features.winding import add_windings_to_assembly

        add_windings_to_assembly(assembly, P)

    return assembly, stator, varnish
