from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cadquery as cq
from cadquery.occ_impl.exporters import assembly as asm_export


@dataclass(frozen=True)
class RGY0020DParams:
    # Package outline (mm): 3.4-3.6 by 4.4-4.6, 1.0 max height.
    body_x: float = 3.5
    body_y: float = 4.5
    body_height: float = 1.0  # seating plane to top
    standoff: float = 0.05  # seating plane to body bottom (0.00-0.05)

    # Terminals (mm): interpreting 20X 0.5/0.3 and 20X 0.3/0.2 as max/min.
    lead_length: float = 0.4  # radial length inward from outer edge
    lead_width: float = 0.25  # along-side width
    lead_height: float = 0.2  # seating plane to top
    lead_pitch: float = 0.5
    leads_per_lr_side: int = 8
    leads_per_td_side: int = 4
    lead_setback: float = 0.0  # flush with package edge

    dimple_width: float = 0.16  # ref. size from side profile
    dimple_height: float = 0.1  # ref. size from section A-A
    dimple_depth: float = 0.13  # ref. size from section A-A

    # Exposed thermal pad (mm): 2.05 ±0.1 by 3.05 ±0.1
    thermal_pad_x: float = 2.05
    thermal_pad_y: float = 3.05
    thermal_pad_thickness: float = 0.05

    # Pin 1 indicator pocket (optional)
    pin1_pocket: float = 0.4
    pin1_depth: float = 0.1
    pin1_margin: float = 0.15


def _positions(count: int, pitch: float) -> list[float]:
    start = -0.5 * (count - 1) * pitch
    return [start + i * pitch for i in range(count)]


def _rounded_lead(length: float, width: float, height: float) -> cq.Workplane:
    radius = width / 2.0
    if length <= radius:
        raise ValueError("Lead length must exceed half the lead width.")
    profile = (
        cq.Workplane("XY")
        .moveTo(-length / 2, -width / 2)
        .lineTo(length / 2 - radius, -width / 2)
        .threePointArc((length / 2, 0), (length / 2 - radius, width / 2))
        .lineTo(-length / 2, width / 2)
        .close()
    )
    return profile.extrude(height)


def _lead_dimple_cut(width: float, height: float, depth: float, lead_offset: float) -> cq.Workplane:
    radius = max(width, height, depth) / 2.0 - 0.000000001
    wp = (
        cq.Workplane("XY")
        .box(depth, width, height, centered=(False, True, False))
        .translate((lead_offset, 0, 0))
    )
    e_on_Z = wp.faces(">Z").edges("|X or >X")
    e_on_X = wp.faces(">X").edges("|Z or >Z")
    return e_on_Z.add(e_on_X).fillet(radius)

def _lead_instances(
    params: RGY0020DParams, prefix: str = "lead", with_spheroid: bool = False
) -> list[tuple[str, cq.Workplane]]:
    base_lead = _rounded_lead(
        params.lead_length, params.lead_width, params.lead_height
    )
    if with_spheroid:
        base_lead = base_lead.cut(
            _lead_dimple_cut(
                params.dimple_width, params.dimple_height, params.dimple_depth, -params.lead_length/2
            )
        )

    leads: list[tuple[str, cq.Workplane]] = []

    lr_positions = _positions(params.leads_per_lr_side, params.lead_pitch)
    x_left = -params.body_x / 2 + params.lead_setback + params.lead_length / 2
    x_right = params.body_x / 2 - params.lead_setback - params.lead_length / 2
    for idx, y in enumerate(lr_positions, start=1):
        left = base_lead.translate((x_left, y, 0))
        right = base_lead.rotate((0, 0, 0), (0, 0, 1), 180).translate((x_right, y, 0))
        leads.append((f"{prefix}_L{idx}", left))
        leads.append((f"{prefix}_R{idx}", right))

    td_positions = _positions(params.leads_per_td_side, params.lead_pitch)
    y_top = params.body_y / 2 - params.lead_setback - params.lead_length / 2
    y_bottom = -params.body_y / 2 + params.lead_setback + params.lead_length / 2
    for idx, x in enumerate(td_positions, start=1):
        top = base_lead.rotate((0, 0, 0), (0, 0, 1), -90).translate((x, y_top, 0))
        bottom = base_lead.rotate((0, 0, 0), (0, 0, 1), 90).translate((x, y_bottom, 0))
        leads.append((f"{prefix}_T{idx}", top))
        leads.append((f"{prefix}_B{idx}", bottom))

    return leads


def _build_body(params: RGY0020DParams) -> cq.Workplane:
    body_thickness = params.body_height - params.standoff
    body = (
        cq.Workplane("XY")
        .box(params.body_x, params.body_y, body_thickness)
        .translate((0, 0, params.standoff + body_thickness / 2))
    )

    # Pin 1 indicator on top-left corner (per drawing "PIN 1 INDEX AREA").
    body = (
        body.faces(">Z")
        .workplane(centerOption="CenterOfMass")
        .moveTo(
            -params.body_x / 2 + params.pin1_margin + params.pin1_pocket / 2,
            params.body_y / 2 - params.pin1_margin - params.pin1_pocket / 2,
        )
        .rect(params.pin1_pocket, params.pin1_pocket)
        .cutBlind(-params.pin1_depth)
    )
    return body


def build_model(params: RGY0020DParams) -> cq.Workplane:
    body = _build_body(params)

    leads_for_cut = _lead_instances(params, prefix="cut", with_spheroid=False)
    leads = _lead_instances(params, with_spheroid=True)
    for _, lead in leads_for_cut:
        body = body.cut(lead)

    model = body
    for _, lead in leads:
        model = model.union(lead)

    # Exposed thermal pad.
    thermal_pad = (
        cq.Workplane("XY")
        .box(params.thermal_pad_x, params.thermal_pad_y, params.thermal_pad_thickness)
        .translate((0, 0, params.thermal_pad_thickness / 2))
    )
    model = model.union(thermal_pad)

    return model


def build_assembly(params: RGY0020DParams) -> cq.Assembly:
    assembly = cq.Assembly()
    body = _build_body(params)
    leads_for_cut = _lead_instances(params, prefix="cut", with_spheroid=False)
    leads = _lead_instances(params, with_spheroid=True)
    for _, lead in leads_for_cut:
        body = body.cut(lead)
    assembly.add(body, name="body")

    for name, lead in leads:
        assembly.add(lead, name=name)

    thermal_pad = (
        cq.Workplane("XY")
        .box(params.thermal_pad_x, params.thermal_pad_y, params.thermal_pad_thickness)
        .translate((0, 0, params.thermal_pad_thickness / 2))
    )
    assembly.add(thermal_pad, name="thermal_pad")

    return assembly


def export_step(model: cq.Workplane | cq.Assembly, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(model, cq.Assembly):
        asm_export.exportAssembly(model, str(out_path))
    else:
        cq.exporters.export(model, str(out_path))


if __name__ == "__main__":
    params = RGY0020DParams()
    result = build_assembly(params)
    export_step(result, Path("rgy0020d.step"))
