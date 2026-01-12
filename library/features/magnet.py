from __future__ import annotations

import math

import cadquery as cq


def deg2rad(d: float) -> float:
    return d * math.pi / 180.0


def polar_xy(r: float, theta_deg: float) -> tuple[float, float]:
    th = deg2rad(theta_deg)
    return (r * math.cos(th), r * math.sin(th))


def rect_solid(L: float, W: float, t: float) -> cq.Workplane:
    return cq.Workplane("XY").rect(L, W).extrude(t, both=True)


def magnet_pockets_and_solids_for_pole(P, pole_center: float, R_mc: float, Lp: float, tp: float, t: float):
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
    b_post = float(m.get("b_post", 0.0))
    dt = (Lp / 2.0) * sin_a + (b_post / 2.0)
    dt_min = (tp / 2.0) + 0.2
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
