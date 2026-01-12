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

    # Hub keepout: prevent any cutters from touching inside this radius.
    # This guarantees the hub stays circular and avoids boolean artifacts.
    hub_keepout_r = R_sh + float(m.get("clearance", 0.0)) + float(b.get("hub_keepout_margin", 4.0))

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

    # Optional clamp: ensure the pocket outer tip stays within the requested outer bridge.
    if m.get("auto_clamp_R_m_c", False):
        bridge = float(m.get("rotor_bridge_od", 0.0))
        clearance = float(m.get("clearance", 0.0))
        outer_limit = R_ro - bridge - clearance
        alpha_rad = math.radians(alpha)
        cos_a = math.cos(alpha_rad)
        R_mc_max = outer_limit - (Lp / 2.0) * cos_a
        if R_mc > R_mc_max:
            print(
                f"WARN: R_m_c ({R_mc:.2f}) too large for rotor_bridge_od; clamping to {R_mc_max:.2f} (outer_limit={outer_limit:.2f})"
            )
            R_mc = R_mc_max

    # Geometry guardrails (conservative)
    alpha_rad = math.radians(alpha)
    sin_a = math.sin(alpha_rad)
    cos_a = math.cos(alpha_rad)

    b_post = float(m.get("b_post", 0.0))
    dt = (Lp / 2.0) * sin_a + (b_post / 2.0)
    dt_min = (tp / 2.0) + 0.2
    if dt < dt_min:
        dt = dt_min

    pocket_cutters = None
    magnet_solids = None

    for i in range(poles):
        pole_center = offset + i * pole_pitch

        pole_pockets, pole_magnets = magnet_pockets_and_solids_for_pole(P, pole_center, R_mc, Lp, tp, t)
        pocket_cutters = pole_pockets if pocket_cutters is None else pocket_cutters.union(pole_pockets)
        if pole_magnets is not None:
            magnet_solids = pole_magnets if magnet_solids is None else magnet_solids.union(pole_magnets)

        # Magnet-aligned barriers (two per pole, one behind each V leg)
        if b.get("aligned_barrier_enabled", False):
            Lb = float(b.get("aligned_barrier_length", 18.0))
            gap = float(b.get("aligned_barrier_gap", 1.5))
            w_extra = float(b.get("aligned_barrier_width_extra", 2.0))
            Wb = tp + w_extra

            # Local basis at pole centerline
            pc = float(pole_center)
            pc_rad = math.radians(pc)
            er = (math.cos(pc_rad), math.sin(pc_rad))
            et = (-math.sin(pc_rad), math.cos(pc_rad))

            # Tangential centroid offset (same rule as magnet.py)
            alpha_rad_local = math.radians(alpha)
            sin_a_local = math.sin(alpha_rad_local)
            b_post_local = float(m.get("b_post", 0.0))
            dt_local = (Lp / 2.0) * sin_a_local + (b_post_local / 2.0)
            dt_min_local = (tp / 2.0) + 0.2
            if dt_local < dt_min_local:
                dt_local = dt_min_local

            for sgn in (+1, -1):
                axis_ang = pc + sgn * alpha
                axis_rad = math.radians(axis_ang)
                u = (math.cos(axis_rad), math.sin(axis_rad))

                # Recompute the magnet pocket centroid (must match magnet.py placement)
                cx = (R_mc * er[0]) + (sgn * dt_local * et[0])
                cy = (R_mc * er[1]) + (sgn * dt_local * et[1])

                # Pocket inner tip (toward shaft) along -u
                tipx = cx - u[0] * (Lp / 2.0)
                tipy = cy - u[1] * (Lp / 2.0)

                # Clamp barrier length so its inner end stays outside the shaft/hub region
                hub_margin = float(b.get("aligned_barrier_hub_margin", 3.0))
                clearance = float(m.get("clearance", 0.0))
                # Never let aligned barriers enter the global hub keepout region (prevents starburst cutouts).
                r_min_allowed = max(
                    R_sh + clearance + hub_margin,
                    hub_keepout_r + float(b.get("aligned_barrier_keepout_extra", 0.2)),
                )

                tip_r = math.hypot(tipx, tipy)
                Lb_eff = float(Lb)
                # Desired inner end radius ≈ tip_r - (gap + Lb_eff)
                if tip_r - (gap + Lb_eff) < r_min_allowed:
                    Lb_eff = max(0.0, tip_r - gap - r_min_allowed)

                # Skip tiny slivers (they create nasty boolean artifacts)
                if Lb_eff <= 0.5:
                    continue

                # Place barrier cavity further inward from inner tip by (gap + Lb_eff/2)
                bx = tipx - u[0] * (gap + Lb_eff / 2.0)
                by = tipy - u[1] * (gap + Lb_eff / 2.0)

                barrier_leg = rect_solid(Lb_eff, Wb, t).rotate((0, 0, 0), (0, 0, 1), axis_ang)
                barrier_leg = barrier_leg.translate((bx, by, 0))

                pocket_cutters = barrier_leg if pocket_cutters is None else pocket_cutters.union(barrier_leg)

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
        # Hub keepout: clip cutters to an annulus so nothing can cut into the hub region.
        if hub_keepout_r < R_ro - 1e-6:
            clip = cq.Workplane("XY").circle(R_ro).circle(hub_keepout_r).extrude(t, both=True)
            pocket_cutters = pocket_cutters.intersect(clip)

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
