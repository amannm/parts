import os
import sys
import types
from pathlib import Path
import cadquery as cq
from cadquery import exporters
from cadquery.occ_impl.exporters import assembly as asm_export
from cadquery.vis import show
from features.magnet import MagnetSpec
from features.stator import StatorSpec, make_stator
from features.winding import WindingSpec
from features.rotor import RotorSpec, make_rotor_and_magnets

P = {
    "global": {
        "poles": 8,
        "slots": 48,
        "airgap": 1.0,
        "angle_offset_deg": 0.0,
        "units": "mm",
    },
    "build": {
        "lam_thickness": 1.0,
        "include_magnets": False,
        "export_enabled": True,
        "export_dir": "./out_ipmsm",
        "export_basename": "ipmsm_singleV",
        "dxf_from_top_face": True,
        "png_enabled": True,
        "png_width": 1400,
        "png_height": 1000,
        "png_edges": True,
        "png_gradient": False,
        "png_trihedron": False,
        "png_bgcolor": (1.0, 1.0, 1.0),
        "show_interactive": True,
    },
    "stator": {
        "D_so": 240.0,
        "D_si": 140.0,
        "b_so": 3.0,
        "b_sn": 5.0,
        "b_sb1": 5.0,
        "b_sb2": 9.0,
        "h_so": 2.0,
        "h_sn": 0.0,
        "h_sb": 23.0,
        "slot_opening_inset": 0.1,
        "slot_style": "semi_closed",
        "fillet_enabled": True,
        "fillet_r": 0.4,
        "varnish_thickness": 0.0,
        "stack_count": 1,
        "steel_color": (0.2, 0.2, 0.2, 1.0),
        "varnish_color": (0.98, 0.72, 0.2, 0.25),
    },
    "rotor": {
        "D_ro": 138.0,
        "D_sh": 70.0,
        "varnish_thickness": 0.0,
        "stack_count": 1,
        "steel_color": (0.2, 0.2, 0.2, 1.0),
        "varnish_color": (0.98, 0.72, 0.2, 0.25),
    },
    "winding": {
        "enabled": False,
        "kind": "hairpin",  # "hairpin" or "wire"
        "slot_clearance": 0.1,
        "varnish_thickness": 0.05,
        "wire_fillet": 0.2,
        "radial_count": 4,
        "tangential_count": 2,
        "conductor_gap": 0.5,
        "copper_color": (0.72, 0.45, 0.2, 1.0),
        "varnish_color": (0.98, 0.72, 0.2, 0.25),
    },
    "magnets": {
        "alpha_v_deg": 60.0,
        "use_center_post_width": False,  # use explicit R_m_c (keeps V pockets at expected radius)
        "b_post": 6.0,
        "b_post_is_outer": False,  # interpret b_post as outer rib width (V opens toward airgap)
        "enforce_rib_clip": True,  # prevents V legs from overlapping into "arrow" pockets
        "L_m": 18.0,
        "t_m": 6.0,
        "clearance": 0.2,
        "R_m_c": 52.0,
        "auto_clamp_R_m_c": True,  # clamp R_m_c to satisfy outer bridge constraint
        "rotor_bridge_od": 1.5,
        "magnet_chamfer": 0.0,
    },
}


def _float_from(mapping, *keys, default=None):
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return float(mapping[key])
    if default is None:
        return None
    return float(default)


def _int_from(mapping, *keys, default=None):
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return int(mapping[key])
    if default is None:
        return None
    return int(default)


def _stator_spec_from_config(cfg: dict) -> StatorSpec:
    g = cfg["global"]
    s = cfg["stator"]
    b = cfg.get("build", {})
    return StatorSpec(
        slots=_int_from(g, "slots", default=0),
        lam_thickness=_float_from(b, "lam_thickness", default=0.0),
        inner_diameter=_float_from(s, "D_si", "stator_inner_diameter", default=0.0),
        outer_diameter=_float_from(s, "D_so", "stator_outer_diameter"),
        yoke_thickness=_float_from(s, "t_y", "yoke_thickness"),
        slot_style=str(s.get("slot_style", s.get("slot_type", "semi_closed"))).lower(),
        slot_opening_inset=_float_from(
            s,
            "slot_opening_inset",
            "bridge_thickness",
            "t_br",
            default=0.0,
        ),
        slot_opening_depth=_float_from(
            s,
            "h_so",
            "slot_opening_depth",
            default=_float_from(s, "h_tt", default=0.0),
        ),
        slot_neck_height=_float_from(s, "h_sn", "slot_neck_height", default=0.0),
        slot_body_height=_float_from(s, "h_sb", "slot_body_height", default=0.0),
        slot_depth=_float_from(s, "h_s", "slot_depth"),
        slot_opening_width=_float_from(s, "b_so", "slot_opening_width"),
        slot_opening_angle_deg=_float_from(s, "alpha_so_deg", "slot_opening_angle_deg"),
        slot_neck_width=_float_from(s, "b_sn", "slot_neck_width", default=_float_from(s, "b_neck")),
        slot_body_top_width=_float_from(
            s,
            "b_sb1",
            "slot_body_width_top",
            default=_float_from(s, "b_s"),
        ),
        slot_body_bottom_width=_float_from(
            s,
            "b_sb2",
            "slot_body_width_bottom",
            default=_float_from(s, "b_s"),
        ),
        slot_pitch_margin=float(s.get("slot_pitch_margin", 0.98)),
        slot_angle_offset_deg=float(s.get("slot_angle_offset_deg", g.get("angle_offset_deg", 0.0))),
        slot_bottom_arc_radius=_float_from(
            s,
            "slot_bottom_arc_radius",
            "bottom_arc_radius",
            "r_sb_arc",
            default=0.0,
        ),
        slot_corner_radius=_float_from(s, "slot_corner_radius", default=0.0),
        slot_mouth_radius=_float_from(s, "r_so_f", "slot_mouth_radius", "slot_opening_fillet", default=0.0),
        tooth_root_radius=_float_from(s, "r_tr", "tooth_root_radius", "tooth_root_fillet", default=0.0),
        slot_bottom_radius=_float_from(s, "r_sb_f", "slot_bottom_radius", "slot_bottom_fillet", default=0.0),
        segment_count=_int_from(s, "segment_count", "N_seg", default=1),
        segment_gap=_float_from(s, "segment_gap", "g_seg", default=0.0),
        segment_gap_deg=_float_from(s, "segment_gap_deg", default=0.0),
        segment_offset_deg=float(s.get("segment_offset_deg", 0.0)),
        segment_radial_margin=float(s.get("segment_radial_margin", 0.1)),
        stack_count=_int_from(s, "stack_count", default=1),
        stack_pitch=_float_from(s, "stack_pitch", default=0.0),
        varnish_thickness=_float_from(s, "varnish_thickness", default=0.0),
        fillet_enabled=bool(s.get("fillet_enabled", False)),
        fillet_r=_float_from(s, "fillet_r", default=0.0),
        steel_color=s.get("steel_color"),
        varnish_color=s.get("varnish_color"),
    )


def _rotor_spec_from_config(cfg: dict) -> RotorSpec:
    g = cfg["global"]
    r = cfg["rotor"]
    b = cfg.get("build", {})
    return RotorSpec(
        poles=_int_from(g, "poles", default=0),
        lam_thickness=_float_from(b, "lam_thickness", default=0.0),
        outer_diameter=_float_from(r, "D_ro", "rotor_outer_diameter", default=0.0),
        shaft_diameter=_float_from(r, "D_sh", "shaft_diameter", default=0.0),
        angle_offset_deg=float(g.get("angle_offset_deg", 0.0)),
        varnish_thickness=_float_from(r, "varnish_thickness", default=0.0),
        stack_count=_int_from(r, "stack_count", default=1),
        stack_pitch=_float_from(r, "stack_pitch", default=0.0),
        steel_color=r.get("steel_color"),
        varnish_color=r.get("varnish_color"),
    )


def _magnet_spec_from_config(cfg: dict) -> MagnetSpec:
    m = cfg["magnets"]
    return MagnetSpec(
        alpha_v_deg=float(m["alpha_v_deg"]),
        L_m=float(m["L_m"]),
        t_m=float(m["t_m"]),
        clearance=float(m["clearance"]),
        R_m_c=float(m["R_m_c"]),
        b_post=float(m.get("b_post", 0.0)),
        magnet_chamfer=float(m.get("magnet_chamfer", 0.0)),
    )


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _export_step(model, out_path: str) -> None:
    if isinstance(model, cq.Assembly):
        asm_export.exportAssembly(model, out_path)
    else:
        exporters.export(model, out_path)


def _build_combined_assembly(stator, rotor, magnets=None) -> cq.Assembly:
    combined = cq.Assembly()
    combined.add(stator, name="stator")
    combined.add(rotor, name="rotor")
    if magnets is not None:
        combined.add(magnets, name="magnets")
    return combined


def export_all(
    stator,
    rotor,
    magnets=None,
    varnish=None,
    stator_steel=None,
    rotor_varnish=None,
    rotor_steel=None,
):
    if not P["build"]["export_enabled"]:
        return
    out_dir = P["build"]["export_dir"]
    base = P["build"]["export_basename"]
    ensure_dir(out_dir)
    _export_step(stator, os.path.join(out_dir, f"{base}_stator.step"))
    _export_step(rotor, os.path.join(out_dir, f"{base}_rotor.step"))
    if varnish is not None:
        exporters.export(varnish, os.path.join(out_dir, f"{base}_stator_varnish.step"))
    if rotor_varnish is not None:
        exporters.export(rotor_varnish, os.path.join(out_dir, f"{base}_rotor_varnish.step"))
    if magnets is not None:
        exporters.export(magnets, os.path.join(out_dir, f"{base}_magnets.step"))
    combined = _build_combined_assembly(stator, rotor, magnets)
    _export_step(combined, os.path.join(out_dir, f"{base}_combined.step"))
    if P["build"].get("dxf_from_top_face", True):
        try:
            dxf_source = stator_steel if stator_steel is not None else stator
            exporters.exportDXF(dxf_source.faces(">Z").val(), os.path.join(out_dir, f"{base}_stator.dxf"))
            rotor_dxf_source = rotor_steel if rotor_steel is not None else rotor
            exporters.exportDXF(rotor_dxf_source.faces(">Z").val(), os.path.join(out_dir, f"{base}_rotor.dxf"))
        except Exception:
            print("WARN: DXF export failed.")
    if P["build"].get("png_enabled", False):
        w = int(P["build"].get("png_width", 1400))
        h = int(P["build"].get("png_height", 1000))
        edges = bool(P["build"].get("png_edges", True))
        gradient = bool(P["build"].get("png_gradient", False))
        trihedron = bool(P["build"].get("png_trihedron", False))
        bgcolor = tuple(P["build"].get("png_bgcolor", (1.0, 1.0, 1.0)))
        show(stator, screenshot=os.path.join(out_dir, f"{base}_stator.png"), interact=False,
             edges=edges, width=w, height=h, gradient=gradient, trihedron=trihedron, bgcolor=bgcolor)
        show(rotor, screenshot=os.path.join(out_dir, f"{base}_rotor.png"), interact=False,
             edges=edges, width=w, height=h, gradient=gradient, trihedron=trihedron, bgcolor=bgcolor)
        if magnets is not None:
            show(magnets, screenshot=os.path.join(out_dir, f"{base}_magnets.png"), interact=False,
                 edges=edges, width=w, height=h, gradient=gradient, trihedron=trihedron, bgcolor=bgcolor)
        show(combined, screenshot=os.path.join(out_dir, f"{base}_combined.png"), interact=False,
             edges=edges, width=w, height=h, gradient=gradient, trihedron=trihedron, bgcolor=bgcolor)


if __name__ == "__main__":
    stator_spec = _stator_spec_from_config(P)
    winding_spec = WindingSpec.from_dict(P.get("winding", {}))
    stator, stator_steel, stator_varnish = make_stator(stator_spec, winding_spec)
    rotor_spec = _rotor_spec_from_config(P)
    magnet_spec = _magnet_spec_from_config(P)
    rotor, rotor_steel, rotor_varnish, magnets = make_rotor_and_magnets(
        rotor_spec,
        magnet_spec,
        include_magnets=P["build"].get("include_magnets", False),
    )
    export_all(stator, rotor, magnets, stator_varnish, stator_steel, rotor_varnish, rotor_steel)
    if P["build"].get("show_interactive", True):
        combined = _build_combined_assembly(stator, rotor, magnets)
        show(combined, width=1280, height=720, interact=True)
