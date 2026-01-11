from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cadquery as cq
from cadquery.occ_impl.exporters import assembly as asm_export

from features.pin import (
    LeadDims,
    LeadLayout,
    add_leads_to_assembly,
    cut_body_for_leads,
    rectangular_lead_sets,
    union_leads,
)
from features.thermal_pad import build_thermal_pad


@dataclass(frozen=True)
class QFNParams:
    # Package outline
    body_x: float = 5.0  # D dimension
    body_y: float = 5.0  # E dimension
    body_height: float = 0.85  # A total height (0.80-0.90, nom 0.85)
    standoff: float = 0.035  # A1 standoff (0.000-0.050, nom 0.035)

    # Lead dimensions
    lead_length: float = 0.35  # L lead length (0.30-0.40, nom 0.35)
    lead_width: float = 0.20  # b lead width (0.15-0.25, nom 0.20)
    lead_height: float = 0.203  # A4 lead thickness (nom 0.203)
    lead_pitch: float = 0.40  # e pitch (nom 0.40)
    lead_setback: float = 0.0  # leads flush with package edge

    # Pin count (10 per side for QFN40)
    leads_per_side: int = 10

    # Exposed thermal pad
    thermal_pad_x: float = 3.6  # D2 (3.5-3.7, nom 3.6)
    thermal_pad_y: float = 3.6  # E2 (3.5-3.7, nom 3.6)
    thermal_pad_thickness: float = 0.08  # A3 (nom 0.08)
    thermal_pad_pin1_chamfer: float = 0.35  # Chamfer on pin 1 corner (0 disables)

    # Lead chamfer (K dimension from spec, applied to outer corners)
    lead_chamfer: float = 0.07  # Chamfer on outer corners of leads

    # Pin 1 marker
    pin1_marker_diameter: float = 0.4
    pin1_marker_depth: float = 0.1


def _build_body(params: QFNParams) -> cq.Workplane:
    body_thickness = params.body_height - params.standoff
    body = (
        cq.Workplane("XY")
        .box(params.body_x, params.body_y, body_thickness)
        .translate((0, 0, params.standoff + body_thickness / 2))
    )
    return body


def _build_pin1_marker(params: QFNParams) -> cq.Workplane:
    marker_x = -params.body_x / 2 + params.body_x * 0.15
    marker_y = params.body_y / 2 - params.body_y * 0.15
    marker_z = params.body_height
    marker = (
        cq.Workplane("XY")
        .workplane(offset=marker_z)
        .moveTo(marker_x, marker_y)
        .circle(params.pin1_marker_diameter / 2)
        .extrude(-params.pin1_marker_depth)
    )
    return marker


def _lead_layout(params: QFNParams) -> LeadLayout:
    return LeadLayout(
        body_x=params.body_x,
        body_y=params.body_y,
        pitch=params.lead_pitch,
        setback=params.lead_setback,
        leads_per_lr_side=params.leads_per_side,
        leads_per_td_side=params.leads_per_side,
    )


def _lead_dims(params: QFNParams) -> LeadDims:
    return LeadDims(
        length=params.lead_length,
        width=params.lead_width,
        height=params.lead_height,
    )


def build_model(params: QFNParams | None = None) -> cq.Workplane:
    if params is None:
        params = QFNParams()
    body = _build_body(params)
    pin1_marker = _build_pin1_marker(params)
    body = body.cut(pin1_marker)
    layout = _lead_layout(params)
    lead_dims = _lead_dims(params)
    lead_sets = rectangular_lead_sets(
        layout,
        lead_dims,
        dimple=None,
        grounded=None,
        profile="chamfered",
        chamfer=params.lead_chamfer,
    )
    body = cut_body_for_leads(body, lead_sets.cuts)
    model = union_leads(body, lead_sets.leads)
    thermal_pad = build_thermal_pad(params)
    model = model.union(thermal_pad)
    return model


def build_assembly(params: QFNParams | None = None) -> cq.Assembly:
    if params is None:
        params = QFNParams()
    assembly = cq.Assembly()
    body = _build_body(params)
    pin1_marker = _build_pin1_marker(params)
    body = body.cut(pin1_marker)
    layout = _lead_layout(params)
    lead_dims = _lead_dims(params)
    lead_sets = rectangular_lead_sets(
        layout,
        lead_dims,
        dimple=None,
        grounded=None,
        profile="chamfered",
        chamfer=params.lead_chamfer,
    )
    body = cut_body_for_leads(body, lead_sets.cuts)
    assembly.add(body, name="body")
    add_leads_to_assembly(assembly, lead_sets.leads)
    thermal_pad = build_thermal_pad(params)
    assembly.add(thermal_pad, name="thermal_pad")
    return assembly


def export_step(model: cq.Workplane | cq.Assembly, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(model, cq.Assembly):
        asm_export.exportAssembly(model, str(out_path))
    else:
        cq.exporters.export(model, str(out_path))


QFN40_5x5 = QFNParams()

if __name__ == "__main__":
    from cadquery.vis import show
    params = QFN40_5x5
    result = build_assembly(params)
    export_step(result, Path("qfn40_5x5.step"))
    show(result, width=1280, height=720, zoom=0, roll=0, elevation=0, interact=True)
