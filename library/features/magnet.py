from __future__ import annotations

import math
from dataclasses import dataclass

import cadquery as cq


@dataclass(frozen=True)
class MagnetSpec:
    alpha_v_deg: float
    L_m: float
    t_m: float
    clearance: float
    R_m_c: float
    b_post: float = 0.0
    magnet_chamfer: float = 0.0


def deg2rad(d: float) -> float:
    return d * math.pi / 180.0


def polar_xy(r: float, theta_deg: float) -> tuple[float, float]:
    th = deg2rad(theta_deg)
    return (r * math.cos(th), r * math.sin(th))


def rect_solid(L: float, W: float, t: float) -> cq.Workplane:
    return cq.Workplane("XY").rect(L, W).extrude(t, both=True)


def magnet_pockets_and_solids_for_pole(
    spec: MagnetSpec,
    pole_center: float,
    pocket_thickness: float,
    magnet_thickness: float | None = None,
    *,
    include_magnets: bool = False,
):
    if magnet_thickness is None:
        magnet_thickness = pocket_thickness
    Lp = float(spec.L_m) + 2.0 * float(spec.clearance)
    tp = float(spec.t_m) + 2.0 * float(spec.clearance)
    R_mc = float(spec.R_m_c)
    pocket_cutters = None
    magnet_solids = None
    pc = float(pole_center)
    pc_rad = deg2rad(pc)
    er = (math.cos(pc_rad), math.sin(pc_rad))
    et = (-math.sin(pc_rad), math.cos(pc_rad))
    alpha_deg = float(spec.alpha_v_deg)
    alpha_rad = deg2rad(alpha_deg)
    sin_a = math.sin(alpha_rad)
    b_post = float(spec.b_post)
    dt = (Lp / 2.0) * sin_a + (b_post / 2.0)
    dt_min = (tp / 2.0) + 0.2
    if abs(dt) < dt_min:
        dt = math.copysign(dt_min, dt if abs(dt) > 1e-9 else 1.0)
    for sgn in (+1, -1):
        axis_ang = pc + sgn * alpha_deg
        cx = (R_mc * er[0]) + (sgn * dt * et[0])
        cy = (R_mc * er[1]) + (sgn * dt * et[1])
        pocket = rect_solid(Lp, tp, pocket_thickness).rotate((0, 0, 0), (0, 0, 1), axis_ang)
        pocket = pocket.translate((cx, cy, 0))
        pocket_cutters = pocket if pocket_cutters is None else pocket_cutters.union(pocket)
        if include_magnets:
            mag = rect_solid(float(spec.L_m), float(spec.t_m), magnet_thickness).rotate(
                (0, 0, 0), (0, 0, 1), axis_ang
            )
            mag = mag.translate((cx, cy, 0))
            ch = float(spec.magnet_chamfer)
            if ch > 0:
                try:
                    mag = mag.edges("|Z").chamfer(ch)
                except Exception:
                    print("WARN: Magnet chamfer failed (try smaller magnet_chamfer).")
            magnet_solids = mag if magnet_solids is None else magnet_solids.union(mag)
    return pocket_cutters, magnet_solids
