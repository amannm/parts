from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import cadquery as cq
from cadquery.occ_impl.exporters import assembly as asm_export
from cadquery.vis import show

from pin import (
    GroundedLeadSpec,
    LeadDims,
    LeadDimple,
    LeadLayout,
    ThermalPadSpec,
    grounded_td_indices,
    rectangular_lead_instances,
    thermal_pad_solids,
)


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
    lead_setback: float = 0.0  # flush with package edge

    leads_per_lr_side: int = 8
    leads_per_td_side: int = 4
    leads_grounded_per_td_side: int = 2

    dimple_width: float = 0.16  # ref. size from side profile
    dimple_height: float = 0.1  # ref. size from section A-A
    dimple_depth: float = 0.13  # ref. size from section A-A

    # Exposed thermal pad (mm): 2.05 ±0.1 by 3.05 ±0.1
    thermal_pad_x: float = 2.05
    thermal_pad_y: float = 3.05
    # Top/bottom strip length extending from thermal pad edge.
    thermal_pad_td_center_strip: float = (4.2 - thermal_pad_y) / 2
    thermal_pad_thickness: float = 0.05


def _build_body(params: RGY0020DParams) -> cq.Workplane:
    body_thickness = params.body_height - params.standoff
    body = (
        cq.Workplane("XY")
        .box(params.body_x, params.body_y, body_thickness)
        .translate((0, 0, params.standoff + body_thickness / 2))
    )
    return body


def _lead_layout(params: RGY0020DParams) -> LeadLayout:
    return LeadLayout(
        body_x=params.body_x,
        body_y=params.body_y,
        pitch=params.lead_pitch,
        setback=params.lead_setback,
        leads_per_lr_side=params.leads_per_lr_side,
        leads_per_td_side=params.leads_per_td_side,
    )


def _lead_dims(params: RGY0020DParams) -> LeadDims:
    return LeadDims(
        length=params.lead_length,
        width=params.lead_width,
        height=params.lead_height,
    )


def _lead_dimple(params: RGY0020DParams) -> LeadDimple:
    return LeadDimple(
        width=params.dimple_width,
        height=params.dimple_height,
        depth=params.dimple_depth,
    )


def _grounded_lead_spec(params: RGY0020DParams) -> GroundedLeadSpec:
    grounded_length = (params.body_y / 2 - params.lead_setback) - (
        params.thermal_pad_y / 2
    )
    return GroundedLeadSpec(
        count_per_td_side=params.leads_grounded_per_td_side,
        length=grounded_length,
        profile="flat",
    )


def _thermal_pad(params: RGY0020DParams) -> ThermalPadSpec:
    return ThermalPadSpec(
        x=params.thermal_pad_x,
        y=params.thermal_pad_y,
        thickness=params.thermal_pad_thickness,
        td_center_strip=params.thermal_pad_td_center_strip,
    )


def _union_solids(solids: list[cq.Workplane]) -> cq.Workplane | None:
    result = None
    for solid in solids:
        result = solid if result is None else result.union(solid)
    return result


def build_model(params: RGY0020DParams) -> cq.Workplane:
    body = _build_body(params)

    layout = _lead_layout(params)
    lead_dims = _lead_dims(params)
    grounded = _grounded_lead_spec(params)
    dimple = _lead_dimple(params)
    grounded_indices = grounded_td_indices(
        layout.leads_per_td_side, params.leads_grounded_per_td_side
    )

    leads_for_cut = rectangular_lead_instances(
        layout, lead_dims, prefix="cut", dimple=None, grounded=grounded
    )
    leads = rectangular_lead_instances(
        layout, lead_dims, dimple=dimple, grounded=grounded
    )
    for _, lead in leads_for_cut:
        body = body.cut(lead)

    model = body
    for _, lead in leads:
        model = model.union(lead)

    for _, solid in thermal_pad_solids(
        _thermal_pad(params),
        layout=layout,
        lead_width=params.lead_width,
        grounded_indices=grounded_indices,
    ):
        model = model.union(solid)

    return model


def build_assembly(params: RGY0020DParams) -> cq.Assembly:
    assembly = cq.Assembly()
    body = _build_body(params)
    layout = _lead_layout(params)
    lead_dims = _lead_dims(params)
    grounded = _grounded_lead_spec(params)
    dimple = _lead_dimple(params)
    grounded_indices = grounded_td_indices(
        layout.leads_per_td_side, params.leads_grounded_per_td_side
    )
    leads_for_cut = rectangular_lead_instances(
        layout, lead_dims, prefix="cut", dimple=None, grounded=grounded
    )
    leads = rectangular_lead_instances(
        layout, lead_dims, dimple=dimple, grounded=grounded
    )
    for _, lead in leads_for_cut:
        body = body.cut(lead)
    assembly.add(body, name="body")
    grounded_leads: list[cq.Workplane] = []
    for name, lead in leads:
        td_index = None
        if name.startswith("lead_T"):
            td_index = int(name[len("lead_T"):])
        elif name.startswith("lead_B"):
            td_index = int(name[len("lead_B"):])
        if td_index in grounded_indices:
            grounded_leads.append(lead)
        else:
            assembly.add(lead, name=name)

    pad_union = _union_solids(
        [
            solid
            for _, solid in thermal_pad_solids(
                _thermal_pad(params),
                layout=layout,
                lead_width=params.lead_width,
                grounded_indices=grounded_indices,
            )
        ]
    )
    grounded_union = _union_solids(grounded_leads)
    if pad_union is not None:
        grounded_union = (
            pad_union if grounded_union is None else grounded_union.union(pad_union)
        )

    if grounded_union is not None:
        assembly.add(grounded_union, name="grounded_pad")

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
    show(result, width=1280, height=720, zoom=0, roll=0, elevation=0, interact=True)
