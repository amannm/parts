"""Single-layer V-type IPMSM 2D lamination generator (CadQuery 2.x)"""

import os
import sys
import types
from pathlib import Path

from cadquery import exporters
from cadquery.vis import show

def _ensure_local_library_pkg() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    library_dir = repo_root / "library"
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    pkg = sys.modules.get("library")
    if pkg is None or library_dir.resolve() not in {
        Path(p).resolve() for p in getattr(pkg, "__path__", [])
    }:
        pkg = types.ModuleType("library")
        pkg.__path__ = [str(library_dir)]
        sys.modules["library"] = pkg


_ensure_local_library_pkg()

from library.features.stator import make_stator
from library.features.rotor import make_rotor_and_magnets


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
    },
    "rotor": {
        "D_ro": 138.0,
        "D_sh": 40.0,
        "keyway_enabled": False,
        "keyway_w": 6.0,
        "keyway_d": 3.0,
        "keyway_angle_deg": 0.0,
        "holes_enabled": False,
        "holes_count": 2,
        "holes_d": 6.0,
        "holes_r": 25.0,
        "holes_angle_offset_deg": 90.0,
    },
    "magnets": {
        "alpha_v_deg": 22.0,
        "use_center_post_width": False,
        "b_post": 6.0,
        "L_m": 30.0,
        "t_m": 6.0,
        "clearance": 0.2,
        "R_m_c": 52.0,
        "rotor_bridge_od": 1.5,
        "magnet_chamfer": 0.0,
    },
    "barriers": {
        # Tip: set arc_barrier_enabled/v_cavity_enabled to False first to verify magnet pocket placement.
        "arc_barrier_enabled": True,
        "arc_r_in": 28.0,
        "arc_r_out": 40.0,
        "arc_span_deg": 30.0,
        "arc_segments": 32,
        "v_cavity_enabled": True,
        "v_cavity_depth": 4.0,
        "v_cavity_inset": 1.0,
    },
}


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def export_all(stator, rotor, magnets=None):
    if not P["build"]["export_enabled"]:
        return

    out_dir = P["build"]["export_dir"]
    base = P["build"]["export_basename"]
    ensure_dir(out_dir)

    exporters.export(stator, os.path.join(out_dir, f"{base}_stator.step"))
    exporters.export(rotor, os.path.join(out_dir, f"{base}_rotor.step"))
    if magnets is not None:
        exporters.export(magnets, os.path.join(out_dir, f"{base}_magnets.step"))

    exporters.export(stator.union(rotor), os.path.join(out_dir, f"{base}_combined.step"))

    if P["build"].get("dxf_from_top_face", True):
        try:
            exporters.exportDXF(stator.faces(">Z").val(), os.path.join(out_dir, f"{base}_stator.dxf"))
            exporters.exportDXF(rotor.faces(">Z").val(), os.path.join(out_dir, f"{base}_rotor.dxf"))
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

        show(stator.union(rotor), screenshot=os.path.join(out_dir, f"{base}_combined.png"), interact=False,
             edges=edges, width=w, height=h, gradient=gradient, trihedron=trihedron, bgcolor=bgcolor)


if __name__ == "__main__":
    stator = make_stator(P)
    rotor, magnets = make_rotor_and_magnets(P)

    export_all(stator, rotor, magnets)

    if P["build"].get("show_interactive", True):
        show(stator.union(rotor), width=1280, height=720, interact=True)
