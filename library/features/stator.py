from __future__ import annotations

import cadquery as cq


def make_slot_cutter(P):
    """
    Returns a *solid* cutter for one slot, located at angle 0 (along +X) with the opening at the bore.
    Slot points are defined in XY, then extruded both directions.
    """
    s = P["stator"]
    t = P["build"]["lam_thickness"]

    R_si = s["D_si"] / 2

    w0 = s["b_so"] / 2
    w1 = s["b_neck"] / 2
    w2 = s["b_s"] / 2

    x0 = R_si + float(s.get("slot_opening_inset", 0.0))
    x1 = R_si + s["h_tt"]
    x2 = R_si + s["h_s"]

    # Polygon (clockwise) around +X axis, slot goes outward (+X)
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

    # Base ring
    stator = (
        cq.Workplane("XY")
        .circle(R_so)
        .circle(R_si)
        .extrude(t, both=True)
    )

    # Slots (cut)
    Qs = int(g["slots"])
    slot_cutter = make_slot_cutter(P)

    for k in range(Qs):
        ang = 360.0 * k / Qs
        c = slot_cutter.rotate((0, 0, 0), (0, 0, 1), ang)
        stator = stator.cut(c)

    # Optional fillet (can be fragile if too large)
    if s.get("fillet_enabled", False) and s.get("fillet_r", 0) > 0:
        try:
            stator = stator.edges("|Z").fillet(s["fillet_r"])
        except Exception:
            print("WARN: Stator fillet failed (try smaller fillet_r).")

    return stator
