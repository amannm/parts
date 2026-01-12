from __future__ import annotations

import math

import cadquery as cq

from features.magnet import magnet_pockets_and_solids_for_pole


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

def make_rotor_and_magnets(P):
    g = P["global"]
    r = P["rotor"]
    m = P["magnets"]
    t = P["build"]["lam_thickness"]
    varnish_thickness = float(r.get("varnish_thickness", 0.0))
    stack_count = int(r.get("stack_count", 1))
    if stack_count < 1:
        stack_count = 1
    stack_pitch = float(r.get("stack_pitch", 0.0))
    if stack_pitch <= 0:
        varnish_pitch = 2.0 * varnish_thickness if varnish_thickness > 0 else 0.0
        stack_pitch = t + varnish_pitch
    magnet_length = t + (stack_count - 1) * stack_pitch
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
        pole_pockets, pole_magnets = magnet_pockets_and_solids_for_pole(
            P,
            pole_center,
            R_mc,
            Lp,
            tp,
            t,
            magnet_length,
        )
        pocket_cutters = pole_pockets if pocket_cutters is None else pocket_cutters.union(pole_pockets)
        if pole_magnets is not None:
            magnet_solids = pole_magnets if magnet_solids is None else magnet_solids.union(pole_magnets)
    if pocket_cutters is not None:
        rotor = rotor.cut(pocket_cutters)

    varnish = None
    if varnish_thickness > 0:
        try:
            varnish = rotor.shell(varnish_thickness, kind="intersection")
        except Exception:
            print("WARN: Rotor varnish shell failed (try smaller varnish_thickness).")

    assembly = cq.Assembly()
    steel_color = _color_from(r.get("steel_color"), (0.25, 0.25, 0.25, 1.0))
    varnish_color = _color_from(r.get("varnish_color"), (0.98, 0.72, 0.2, 0.25))
    z0 = -0.5 * (stack_count - 1) * stack_pitch
    for idx in range(stack_count):
        z = z0 + idx * stack_pitch
        if varnish is not None:
            assembly.add(
                varnish.translate((0, 0, z)),
                name=f"rotor_varnish_{idx}",
                color=varnish_color,
            )
        assembly.add(
            rotor.translate((0, 0, z)),
            name=f"rotor_steel_{idx}",
            color=steel_color,
        )

    return assembly, rotor, varnish, magnet_solids
