from __future__ import annotations

import os
from dataclasses import dataclass

import cadquery as cq
from cadquery import exporters
from cadquery.occ_impl.exporters import assembly as asm_export
from cadquery.vis import show

from features.magnet import MagnetSpec
from features.rotor import RotorSpec, build_rotor_and_magnets
from features.stator import StatorSpec, build_stator
from features.winding import WindingSpec


@dataclass(frozen=True)
class GlobalConfig:
    poles: int = 8
    slots: int = 48
    airgap: float = 1.0
    angle_offset_deg: float = 0.0
    units: str = "mm"


@dataclass(frozen=True)
class BuildConfig:
    lam_thickness: float = 1.0
    include_magnets: bool = False
    export_enabled: bool = True
    export_dir: str = "./out_ipmsm"
    export_basename: str = "ipmsm_singleV"
    dxf_from_top_face: bool = True
    png_enabled: bool = True
    png_width: int = 1400
    png_height: int = 1000
    png_edges: bool = True
    png_gradient: bool = False
    png_trihedron: bool = False
    png_bgcolor: tuple[float, float, float] = (1.0, 1.0, 1.0)
    show_interactive: bool = True


@dataclass(frozen=True)
class StatorConfig:
    D_so: float = 240.0
    D_si: float = 140.0
    b_so: float = 3.0
    b_sn: float = 5.0
    b_sb1: float = 5.0
    b_sb2: float = 9.0
    h_so: float = 2.0
    h_sn: float = 0.0
    h_sb: float = 23.0
    slot_opening_inset: float = 0.1
    slot_style: str = "semi_closed"
    fillet_enabled: bool = True
    fillet_r: float = 0.4
    varnish_thickness: float = 0.0
    stack_count: int = 1
    steel_color: tuple[float, float, float, float] | None = (0.2, 0.2, 0.2, 1.0)
    varnish_color: tuple[float, float, float, float] | None = (0.98, 0.72, 0.2, 0.25)


@dataclass(frozen=True)
class RotorConfig:
    D_ro: float = 138.0
    D_sh: float = 70.0
    varnish_thickness: float = 0.0
    stack_count: int = 1
    steel_color: tuple[float, float, float, float] | None = (0.2, 0.2, 0.2, 1.0)
    varnish_color: tuple[float, float, float, float] | None = (0.98, 0.72, 0.2, 0.25)


@dataclass(frozen=True)
class WindingConfig:
    enabled: bool = False
    kind: str = "hairpin"
    slot_clearance: float = 0.1
    varnish_thickness: float = 0.05
    wire_fillet: float = 0.2
    radial_count: int = 4
    tangential_count: int = 2
    conductor_gap: float = 0.5
    copper_color: tuple[float, float, float, float] | None = (0.72, 0.45, 0.2, 1.0)
    varnish_color: tuple[float, float, float, float] | None = (0.98, 0.72, 0.2, 0.25)


@dataclass(frozen=True)
class MagnetConfig:
    alpha_v_deg: float = 60.0
    use_center_post_width: bool = False
    b_post: float = 6.0
    b_post_is_outer: bool = False
    enforce_rib_clip: bool = True
    L_m: float = 18.0
    t_m: float = 6.0
    clearance: float = 0.2
    R_m_c: float = 52.0
    auto_clamp_R_m_c: bool = True
    rotor_bridge_od: float = 1.5
    magnet_chamfer: float = 0.0


@dataclass(frozen=True)
class IPMSMConfig:
    global_: GlobalConfig = GlobalConfig()
    build: BuildConfig = BuildConfig()
    stator: StatorConfig = StatorConfig()
    rotor: RotorConfig = RotorConfig()
    winding: WindingConfig = WindingConfig()
    magnets: MagnetConfig = MagnetConfig()


def _stator_spec_from_config(cfg: IPMSMConfig) -> StatorSpec:
    g = cfg.global_
    s = cfg.stator
    b = cfg.build
    return StatorSpec(
        slots=g.slots,
        lam_thickness=b.lam_thickness,
        inner_diameter=s.D_si,
        outer_diameter=s.D_so,
        slot_style=s.slot_style,
        slot_opening_inset=s.slot_opening_inset,
        slot_opening_depth=s.h_so,
        slot_neck_height=s.h_sn,
        slot_body_height=s.h_sb,
        slot_opening_width=s.b_so,
        slot_neck_width=s.b_sn,
        slot_body_top_width=s.b_sb1,
        slot_body_bottom_width=s.b_sb2,
        slot_angle_offset_deg=g.angle_offset_deg,
        stack_count=s.stack_count,
        varnish_thickness=s.varnish_thickness,
        fillet_enabled=s.fillet_enabled,
        fillet_r=s.fillet_r,
        steel_color=s.steel_color,
        varnish_color=s.varnish_color,
    )


def _rotor_spec_from_config(cfg: IPMSMConfig) -> RotorSpec:
    g = cfg.global_
    r = cfg.rotor
    b = cfg.build
    return RotorSpec(
        poles=g.poles,
        lam_thickness=b.lam_thickness,
        outer_diameter=r.D_ro,
        shaft_diameter=r.D_sh,
        angle_offset_deg=g.angle_offset_deg,
        varnish_thickness=r.varnish_thickness,
        stack_count=r.stack_count,
        steel_color=r.steel_color,
        varnish_color=r.varnish_color,
    )


def _magnet_spec_from_config(cfg: IPMSMConfig) -> MagnetSpec:
    m = cfg.magnets
    return MagnetSpec(
        alpha_v_deg=m.alpha_v_deg,
        L_m=m.L_m,
        t_m=m.t_m,
        clearance=m.clearance,
        R_m_c=m.R_m_c,
        b_post=m.b_post,
        magnet_chamfer=m.magnet_chamfer,
    )


def _winding_spec_from_config(cfg: IPMSMConfig) -> WindingSpec:
    w = cfg.winding
    return WindingSpec(
        kind=w.kind,
        slot_clearance=w.slot_clearance,
        varnish_thickness=w.varnish_thickness,
        wire_fillet=w.wire_fillet,
        radial_count=w.radial_count,
        tangential_count=w.tangential_count,
        conductor_gap=w.conductor_gap,
        copper_color=w.copper_color,
        varnish_color=w.varnish_color,
    )


def _ensure_dir(path: str) -> None:
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
    cfg: IPMSMConfig,
    stator,
    rotor,
    magnets=None,
    varnish=None,
    stator_steel=None,
    rotor_varnish=None,
    rotor_steel=None,
):
    if not cfg.build.export_enabled:
        return
    out_dir = cfg.build.export_dir
    base = cfg.build.export_basename
    _ensure_dir(out_dir)
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
    if cfg.build.dxf_from_top_face:
        try:
            dxf_source = stator_steel if stator_steel is not None else stator
            exporters.exportDXF(dxf_source.faces(">Z").val(), os.path.join(out_dir, f"{base}_stator.dxf"))
            rotor_dxf_source = rotor_steel if rotor_steel is not None else rotor
            exporters.exportDXF(rotor_dxf_source.faces(">Z").val(), os.path.join(out_dir, f"{base}_rotor.dxf"))
        except Exception:
            print("WARN: DXF export failed.")
    if cfg.build.png_enabled:
        w = cfg.build.png_width
        h = cfg.build.png_height
        edges = cfg.build.png_edges
        gradient = cfg.build.png_gradient
        trihedron = cfg.build.png_trihedron
        bgcolor = cfg.build.png_bgcolor
        show(stator, screenshot=os.path.join(out_dir, f"{base}_stator.png"), interact=False,
             edges=edges, width=w, height=h, gradient=gradient, trihedron=trihedron, bgcolor=bgcolor)
        show(rotor, screenshot=os.path.join(out_dir, f"{base}_rotor.png"), interact=False,
             edges=edges, width=w, height=h, gradient=gradient, trihedron=trihedron, bgcolor=bgcolor)
        if magnets is not None:
            show(magnets, screenshot=os.path.join(out_dir, f"{base}_magnets.png"), interact=False,
                 edges=edges, width=w, height=h, gradient=gradient, trihedron=trihedron, bgcolor=bgcolor)
        show(combined, screenshot=os.path.join(out_dir, f"{base}_combined.png"), interact=False,
             edges=edges, width=w, height=h, gradient=gradient, trihedron=trihedron, bgcolor=bgcolor)


def build_ipmsm(cfg: IPMSMConfig | None = None):
    if cfg is None:
        cfg = IPMSMConfig()
    stator_spec = _stator_spec_from_config(cfg)
    winding_spec = _winding_spec_from_config(cfg) if cfg.winding.enabled else None
    stator, stator_steel, stator_varnish = build_stator(stator_spec, winding_spec)
    rotor_spec = _rotor_spec_from_config(cfg)
    magnet_spec = _magnet_spec_from_config(cfg)
    rotor, rotor_steel, rotor_varnish, magnets = build_rotor_and_magnets(
        rotor_spec,
        magnet_spec,
        include_magnets=cfg.build.include_magnets,
    )
    return stator, stator_steel, stator_varnish, rotor, rotor_steel, rotor_varnish, magnets


if __name__ == "__main__":
    cfg = IPMSMConfig()
    stator, stator_steel, stator_varnish, rotor, rotor_steel, rotor_varnish, magnets = build_ipmsm(cfg)
    export_all(cfg, stator, rotor, magnets, stator_varnish, stator_steel, rotor_varnish, rotor_steel)
    if cfg.build.show_interactive:
        combined = _build_combined_assembly(stator, rotor, magnets)
        show(combined, width=1280, height=720, interact=True)
