from __future__ import annotations

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


def make_slot_cutter(P):
    s = P["stator"]
    t = P["build"]["lam_thickness"]
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
    slot = (
        cq.Workplane("XY")
        .polyline(pts)
        .close()
        .extrude(t, both=True)
    )
    return slot


def make_stator(P):
    g = P["global"]
    s = P["stator"]
    t = P["build"]["lam_thickness"]
    R_so = s["D_so"] / 2
    R_si = s["D_si"] / 2
    stator = (
        cq.Workplane("XY")
        .circle(R_so)
        .circle(R_si)
        .extrude(t, both=True)
    )
    Qs = int(g["slots"])
    slot_cutter = make_slot_cutter(P)
    for k in range(Qs):
        ang = 360.0 * k / Qs
        c = slot_cutter.rotate((0, 0, 0), (0, 0, 1), ang)
        stator = stator.cut(c)
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
