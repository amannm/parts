import os
import sys
import types
from pathlib import Path
import cadquery as cq
from cadquery import exporters
from cadquery.occ_impl.exporters import assembly as asm_export
from cadquery.vis import show
from features.stator import make_stator
from features.rotor import make_rotor_and_magnets

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
        "include_magnets": True,
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
        "b_neck": 5.0,
        "b_s": 9.0,
        "h_tt": 2.0,
        "h_s": 25.0,
        "slot_opening_inset": 0.1,
        "fillet_enabled": True,
        "fillet_r": 0.4,
        "varnish_thickness": 0.1,
        "stack_count": 20,
        "steel_color": (0.2, 0.2, 0.2, 1.0),
        "varnish_color": (0.98, 0.72, 0.2, 0.25),
    },
    "rotor": {
        "D_ro": 138.0,
        "D_sh": 70.0,
        "varnish_thickness": 0.1,
        "stack_count": 20,
        "steel_color": (0.2, 0.2, 0.2, 1.0),
        "varnish_color": (0.98, 0.72, 0.2, 0.25),
    },
    "winding": {
        "enabled": True,
        "kind": "hairpin",  # "hairpin" or "wire"
        "slot_clearance": 0.1,
        "varnish_thickness": 0.05,
        "wire_fillet": 0.2,
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
    stator, stator_steel, stator_varnish = make_stator(P)
    rotor, rotor_steel, rotor_varnish, magnets = make_rotor_and_magnets(P)
    export_all(stator, rotor, magnets, stator_varnish, stator_steel, rotor_varnish, rotor_steel)
    if P["build"].get("show_interactive", True):
        combined = _build_combined_assembly(stator, rotor, magnets)
        show(combined, width=1280, height=720, interact=True)
