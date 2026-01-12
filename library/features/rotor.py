from __future__ import annotations

import math

import cadquery as cq

from magnet import (
    compute_Rmc_from_post,
    magnet_pockets_and_solids_for_pole,
    polar_xy,
    rect_solid,
)


def annulus_sector_solid(r_in, r_out, a_center_deg, span_deg, t, nseg=32):
    """Approximate an annulus sector with a closed polyline (outer arc then inner arc reversed)."""
    a1 = a_center_deg - span_deg / 2
    a2 = a_center_deg + span_deg / 2
    outer = [polar_xy(r_out, a1 + (a2 - a1) * i / nseg) for i in range(nseg + 1)]
    inner = [polar_xy(r_in, a2 - (a2 - a1) * i / nseg) for i in range(nseg + 1)]
    pts = outer + inner
    return cq.Workplane("XY").polyline(pts).close().extrude(t, both=True)


def make_rotor_and_magnets(P):
    """Returns (rotor_steel_solid, magnets_solid_or_None)."""
    g = P["global"]
    r = P["rotor"]
    m = P["magnets"]
    b = P["barriers"]
    t = P["build"]["lam_thickness"]
    poles = int(g["poles"])
    pole_pitch = 360.0 / float(poles)
    offset = float(g.get("angle_offset_deg", 0.0))
    R_ro = float(r["D_ro"]) / 2.0
    R_sh = float(r["D_sh"]) / 2.0
    rotor = cq.Workplane("XY").circle(R_ro).circle(R_sh).extrude(t, both=True)
    Lp = float(m["L_m"]) + 2.0 * float(m["clearance"])
    tp = float(m["t_m"]) + 2.0 * float(m["clearance"])
    alpha = float(m["alpha_v_deg"])
    R_mc = float(m["R_m_c"])
    alpha_rad = math.radians(alpha)
    sin_a = math.sin(alpha_rad)
    cos_a = math.cos(alpha_rad)
    b_post = float(m.get("b_post", 0.0))
    dt = (Lp / 2.0) * sin_a + (b_post / 2.0)
    dt_min = (tp / 2.0) + 0.2
    pocket_cutters = None
    magnet_solids = None
    for i in range(poles):
        pole_center = offset + i * pole_pitch
        pole_pockets, pole_magnets = magnet_pockets_and_solids_for_pole(P, pole_center, R_mc, Lp, tp, t)
        pocket_cutters = pole_pockets if pocket_cutters is None else pocket_cutters.union(pole_pockets)
        if pole_magnets is not None:
            magnet_solids = pole_magnets if magnet_solids is None else magnet_solids.union(pole_magnets)
    if pocket_cutters is not None:
        rotor = rotor.cut(pocket_cutters)
    return rotor, magnet_solids
