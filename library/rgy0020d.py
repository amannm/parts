from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import cadquery as cq
from cadquery.vis import show
from features.package import build_body, export_step, union_solids
from features.pin import (
    GroundedLeadSpec,
    LeadDims,
    LeadDimple,
    LeadLayout,
    add_leads_to_assembly,
    cut_body_for_leads,
    grounded_td_indices,
    rectangular_pin_sets,
    split_grounded_td_leads,
    union_leads,
)
from features.thermal_pad import thermal_pad_solids_for_params


@dataclass(frozen=True)
class RGY0020DParams:
    # Package outline (mm): 3.4-3.6 by 4.4-4.6, 1.0 max height.
    body_x: float = 3.5
    body_y: float = 4.5
    body_height: float = 1.0  # seating plane to top
    standoff: float = 0.05  # seating plane to body bottom (0.00-0.05)

    # Terminals (mm): interpreting 20X 0.5/0.3 and 20X 0.3/0.2 as max/min.
    pin_length: float = 0.4  # radial length inward from outer edge
    pin_width: float = 0.25  # along-side width
    pin_height: float = 0.2  # seating plane to top
    pin_pitch: float = 0.5
    pin_setback: float = 0.0  # flush with package edge

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
    thermal_pad_pin1_chamfer: float = 0.25  # Chamfer on pin 1 corner (0 disables)


def _pin_layout(params: RGY0020DParams) -> LeadLayout:
    return LeadLayout(
        body_x=params.body_x,
        body_y=params.body_y,
        pitch=params.pin_pitch,
        setback=params.pin_setback,
        leads_per_lr_side=params.leads_per_lr_side,
        leads_per_td_side=params.leads_per_td_side,
    )


def _pin_dims(params: RGY0020DParams) -> LeadDims:
    return LeadDims(
        length=params.pin_length,
        width=params.pin_width,
        height=params.pin_height,
    )


def _pin_dimple(params: RGY0020DParams) -> LeadDimple:
    return LeadDimple(
        width=params.dimple_width,
        height=params.dimple_height,
        depth=params.dimple_depth,
    )


def _grounded_pin_spec(params: RGY0020DParams) -> GroundedLeadSpec:
    grounded_length = (params.body_y / 2 - params.pin_setback) - (
            params.thermal_pad_y / 2
    )
    return GroundedLeadSpec(
        count_per_td_side=params.leads_grounded_per_td_side,
        length=grounded_length,
        profile="flat",
    )


def build_model(params: RGY0020DParams) -> cq.Workplane:
    body = build_body(params)
    layout = _pin_layout(params)
    pin_dims = _pin_dims(params)
    grounded = _grounded_pin_spec(params)
    dimple = _pin_dimple(params)
    grounded_indices = grounded_td_indices(
        layout.leads_per_td_side, params.leads_grounded_per_td_side
    )
    pin_sets = rectangular_pin_sets(
        layout,
        pin_dims,
        dimple=dimple,
        grounded=grounded,
    )
    body = cut_body_for_leads(body, pin_sets.cuts)
    model = union_leads(body, pin_sets.leads)
    for _, solid in thermal_pad_solids_for_params(
            params,
            layout=layout,
            pin_width=params.pin_width,
            grounded_indices=grounded_indices,
    ):
        model = model.union(solid)
    return model


def build_assembly(params: RGY0020DParams) -> cq.Assembly:
    assembly = cq.Assembly()
    body = build_body(params)
    layout = _pin_layout(params)
    pin_dims = _pin_dims(params)
    grounded = _grounded_pin_spec(params)
    dimple = _pin_dimple(params)
    grounded_indices = grounded_td_indices(
        layout.leads_per_td_side, params.leads_grounded_per_td_side
    )
    pin_sets = rectangular_pin_sets(
        layout,
        pin_dims,
        dimple=dimple,
        grounded=grounded,
    )
    body = cut_body_for_leads(body, pin_sets.cuts)
    assembly.add(body, name="body")
    grounded_entries, ungrounded_entries = split_grounded_td_leads(
        pin_sets.leads,
        grounded_indices,
    )
    add_leads_to_assembly(assembly, ungrounded_entries)
    grounded_leads = [lead for _, lead in grounded_entries]
    pad_solids: list[cq.Workplane] = []
    for _, solid in thermal_pad_solids_for_params(
            params,
            layout=layout,
            pin_width=params.pin_width,
            grounded_indices=grounded_indices,
    ):
        pad_solids.append(solid)
    pad_union = union_solids(pad_solids)
    grounded_union = union_solids(grounded_leads)
    if pad_union is not None:
        grounded_union = (
            pad_union if grounded_union is None else grounded_union.union(pad_union)
        )
    if grounded_union is not None:
        assembly.add(grounded_union, name="grounded_pad")
    return assembly


if __name__ == "__main__":
    params = RGY0020DParams()
    result = build_assembly(params)
    export_step(result, Path("rgy0020d.step"))
    show(result, width=1280, height=720, zoom=0, roll=0, elevation=0, interact=True)
