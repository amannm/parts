from __future__ import annotations

import math

import cadquery as cq


def deg2rad(d: float) -> float:
    return d * math.pi / 180.0


def polar_xy(r: float, theta_deg: float) -> tuple[float, float]:
    """theta_deg measured from +X, CCW."""
    th = deg2rad(theta_deg)
    return (r * math.cos(th), r * math.sin(th))


def rect_solid(L: float, W: float, t: float) -> cq.Workplane:
    """Centered rectangle extruded symmetrically about the XY plane."""
    return cq.Workplane("XY").rect(L, W).extrude(t, both=True)


def compute_Rmc_from_post(P) -> float:
    """Approximate magnet centroid radius R_mc from a desired inner-tip separation.

    b_post is interpreted as the approximate tangential separation of the *inner tips*.

    Relations (approx):
    - b_post ≈ 2 * r_in_tip * sin(alpha)
    - r_in_tip = R_mc - (Lp/2)*cos(alpha)

    We also clamp to maintain the specified outer bridge.
    """
    m = P["magnets"]
    r = P["rotor"]

    alpha_rad = deg2rad(float(m["alpha_v_deg"]))
    sin_a = max(1e-6, math.sin(alpha_rad))
    cos_a = math.cos(alpha_rad)

    Lp = float(m["L_m"]) + 2.0 * float(m["clearance"])

    r_in_tip_target = float(m["b_post"]) / (2.0 * sin_a)
    R_mc = r_in_tip_target + (Lp / 2.0) * cos_a

    R_ro = float(r["D_ro"]) / 2.0
    bridge = float(m["rotor_bridge_od"])
    clearance = float(m["clearance"])
    outer_limit = R_ro - bridge - clearance
    R_mc_max = outer_limit - (Lp / 2.0) * cos_a
    if R_mc > R_mc_max:
        R_mc = R_mc_max

    return R_mc


def magnet_pockets_and_solids_for_pole(P, pole_center: float, R_mc: float, Lp: float, tp: float, t: float):
    """Two rectangular pockets per pole (single-layer V)."""
    m = P["magnets"]
    pocket_cutters = None
    magnet_solids = None

    pc = float(pole_center)
    pc_rad = deg2rad(pc)
    er = (math.cos(pc_rad), math.sin(pc_rad))
    et = (-math.sin(pc_rad), math.cos(pc_rad))

    alpha_deg = float(m["alpha_v_deg"])
    alpha_rad = deg2rad(alpha_deg)
    sin_a = math.sin(alpha_rad)

    # Tangential centroid offset.
    # Default: b_post defines inner-tip separation.
    # If b_post_is_outer=True: b_post defines the *outer* rib width (outer tips separation),
    # which makes the V open toward the airgap like a typical IPMSM V-type.
    b_post = float(m.get("b_post", 0.0))
    if bool(m.get("b_post_is_outer", False)):
        # outer_sep = 2*dt + Lp*sin(alpha)  =>  dt = (b_post - Lp*sin(alpha))/2
        dt = (b_post / 2.0) - (Lp / 2.0) * sin_a
    else:
        # inner_sep = 2*dt - Lp*sin(alpha)  =>  dt = (Lp*sin(alpha) + b_post)/2
        dt = (Lp / 2.0) * sin_a + (b_post / 2.0)

    dt_min = (tp / 2.0) + 0.2
    # Enforce a minimum centroid separation magnitude to avoid overlapping pockets.
    if abs(dt) < dt_min:
        dt = math.copysign(dt_min, dt if abs(dt) > 1e-9 else 1.0)

    for sgn in (+1, -1):
        axis_ang = pc + sgn * alpha_deg

        cx = (R_mc * er[0]) + (sgn * dt * et[0])
        cy = (R_mc * er[1]) + (sgn * dt * et[1])

        pocket = rect_solid(Lp, tp, t).rotate((0, 0, 0), (0, 0, 1), axis_ang)
        pocket = pocket.translate((cx, cy, 0))
        pocket_cutters = pocket if pocket_cutters is None else pocket_cutters.union(pocket)

        if P["build"].get("include_magnets", False):
            mag = rect_solid(float(m["L_m"]), float(m["t_m"]), t).rotate((0, 0, 0), (0, 0, 1), axis_ang)
            mag = mag.translate((cx, cy, 0))

            ch = float(m.get("magnet_chamfer", 0.0))
            if ch > 0:
                try:
                    mag = mag.edges("|Z").chamfer(ch)
                except Exception:
                    print("WARN: Magnet chamfer failed (try smaller magnet_chamfer).")

            magnet_solids = mag if magnet_solids is None else magnet_solids.union(mag)

    return pocket_cutters, magnet_solids
