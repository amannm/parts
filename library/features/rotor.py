from __future__ import annotations

import math

import cadquery as cq

from library.features.magnet import (
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

    # Guardrail: prevent arc-barrier span from overlapping into adjacent poles.
    arc_span_eff = None
    if b.get("arc_barrier_enabled", False):
        span_req = float(b.get("arc_span_deg", 0.0))
        span_cap = 0.85 * pole_pitch
        arc_span_eff = min(span_req, span_cap)
        if arc_span_eff < span_req:
            print(
                f"WARN: arc_span_deg ({span_req:.1f}) >= pole_pitch; capping to {arc_span_eff:.1f} to avoid overlap. "
                f"(pole_pitch={pole_pitch:.1f})"
            )

    R_ro = float(r["D_ro"]) / 2.0
    R_sh = float(r["D_sh"]) / 2.0

    # Base rotor disk
    rotor = cq.Workplane("XY").circle(R_ro).circle(R_sh).extrude(t, both=True)

    # Optional keyway cut in shaft bore
    if r.get("keyway_enabled", False):
        kw_w = float(r["keyway_w"])
        kw_d = float(r["keyway_d"])
        kw_ang = float(r.get("keyway_angle_deg", 0.0))

        key = rect_solid(kw_d, kw_w, t)
        key = key.translate((R_sh - kw_d / 2.0, 0, 0)).rotate((0, 0, 0), (0, 0, 1), kw_ang)
        rotor = rotor.cut(key)

    # Pocket dimensions
    Lp = float(m["L_m"]) + 2.0 * float(m["clearance"])
    tp = float(m["t_m"]) + 2.0 * float(m["clearance"])
    alpha = float(m["alpha_v_deg"])

    # Determine magnet centroid radius
    if m.get("use_center_post_width", False):
        R_mc = float(compute_Rmc_from_post(P))
    else:
        R_mc = float(m["R_m_c"])

    # Geometry guardrails (conservative)
    alpha_rad = math.radians(alpha)
    sin_a = math.sin(alpha_rad)
    cos_a = math.cos(alpha_rad)

    b_post = float(m.get("b_post", 0.0))
    dt = (Lp / 2.0) * sin_a + (b_post / 2.0)
    dt_min = (tp / 2.0) + 0.2
    if dt < dt_min:
        dt = dt_min

    reach_r = (Lp / 2.0) * cos_a + (tp / 2.0) * sin_a
    reach_t = dt + (Lp / 2.0) * sin_a + (tp / 2.0) * cos_a
    max_r = math.hypot(R_mc + reach_r, reach_t)

    max_allowed = R_ro - float(m["rotor_bridge_od"]) - float(m["clearance"])
    if max_r > max_allowed:
        print(
            f"WARN: Magnet pocket likely breaks outer bridge. "
            f"max_r={max_r:.2f} > {max_allowed:.2f} (allowed)."
        )

    min_allowed = R_sh + float(m["clearance"])
    min_r = math.hypot(
        max(0.0, R_mc - reach_r),
        max(0.0, abs(dt) - ((Lp / 2.0) * sin_a + (tp / 2.0) * cos_a)),
    )
    if min_r < min_allowed:
        print(
            f"WARN: Magnet pocket likely cuts into shaft/hub. "
            f"min_r={min_r:.2f} < {min_allowed:.2f} (min allowed)."
        )

    pocket_cutters = None
    magnet_solids = None

    for i in range(poles):
        pole_center = offset + i * pole_pitch

        pole_pockets, pole_magnets = magnet_pockets_and_solids_for_pole(P, pole_center, R_mc, Lp, tp, t)
        pocket_cutters = pole_pockets if pocket_cutters is None else pocket_cutters.union(pole_pockets)
        if pole_magnets is not None:
            magnet_solids = pole_magnets if magnet_solids is None else magnet_solids.union(pole_magnets)

        # Optional: arc barrier cavity per pole (annulus sector)
        if b.get("arc_barrier_enabled", False):
            barrier = annulus_sector_solid(
                r_in=float(b["arc_r_in"]),
                r_out=float(b["arc_r_out"]),
                a_center_deg=pole_center,
                span_deg=(arc_span_eff if arc_span_eff is not None else float(b["arc_span_deg"])),
                t=t,
                nseg=int(b.get("arc_segments", 32)),
            )
            pocket_cutters = barrier if pocket_cutters is None else pocket_cutters.union(barrier)

        # Optional: V-cavity behind magnet inner tips (triangular)
        if b.get("v_cavity_enabled", False):
            pc = float(pole_center)
            pc_rad = math.radians(pc)
            er = (math.cos(pc_rad), math.sin(pc_rad))
            et = (-math.sin(pc_rad), math.cos(pc_rad))

            alpha_rad = math.radians(alpha)
            sin_a = math.sin(alpha_rad)
            cos_a = math.cos(alpha_rad)

            b_post = float(m.get("b_post", 0.0))
            dt = (Lp / 2.0) * sin_a + (b_post / 2.0)
            dt_min = (tp / 2.0) + 0.2
            if dt < dt_min:
                dt = dt_min

            r_in_base = R_mc - (Lp / 2.0) * cos_a
            t_in_base = dt - (Lp / 2.0) * sin_a
            p1 = (r_in_base * er[0] + t_in_base * et[0], r_in_base * er[1] + t_in_base * et[1])
            p2 = (r_in_base * er[0] - t_in_base * et[0], r_in_base * er[1] - t_in_base * et[1])

            inset = float(b.get("v_cavity_inset", 0.0))
            if inset > 0:
                def inset_point(p):
                    x, y = p
                    rr = math.hypot(x, y)
                    rr2 = max(0.0, rr - inset)
                    if rr < 1e-9:
                        return p
                    return (x * rr2 / rr, y * rr2 / rr)

                p1 = inset_point(p1)
                p2 = inset_point(p2)

            apex_r = max(0.0, r_in_base - float(b.get("v_cavity_depth", 0.0)))
            apex = polar_xy(apex_r, pole_center)

            tri = cq.Workplane("XY").polyline([p1, apex, p2]).close().extrude(t, both=True)
            pocket_cutters = tri if pocket_cutters is None else pocket_cutters.union(tri)

    if pocket_cutters is not None:
        rotor = rotor.cut(pocket_cutters)

    # Optional balance holes
    if r.get("holes_enabled", False):
        holes = None
        for k in range(int(r["holes_count"])):
            ang = float(r.get("holes_angle_offset_deg", 0.0)) + 360.0 * k / float(r["holes_count"])
            x, y = polar_xy(float(r["holes_r"]), ang)
            h = cq.Workplane("XY").center(x, y).circle(float(r["holes_d"]) / 2.0).extrude(t, both=True)
            holes = h if holes is None else holes.union(h)
        rotor = rotor.cut(holes)

    return rotor, magnet_solids
