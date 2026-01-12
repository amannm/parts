from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import cadquery as cq
from cadquery import selectors

from library.features.pin import LeadLayout, positions


@dataclass(frozen=True)
class ThermalPadSpec:
    x: float
    y: float
    thickness: float
    td_center_strip: float = 0.0


class ThermalPadParams(Protocol):
    thermal_pad_x: float
    thermal_pad_y: float
    thermal_pad_thickness: float
    thermal_pad_pin1_chamfer: float


class ThermalPadStripParams(ThermalPadParams, Protocol):
    thermal_pad_td_center_strip: float


def _chamfer_pin1_pad_corner(
    pad: cq.Workplane,
    *,
    pad_x: float,
    pad_y: float,
    pad_thickness: float,
    chamfer: float,
) -> cq.Workplane:
    if chamfer <= 0:
        return pad
    half_x = pad_x / 2
    half_y = pad_y / 2
    max_chamfer = min(half_x, half_y) * 0.99
    c = min(chamfer, max_chamfer)
    corner = (-half_x, half_y, pad_thickness / 2)
    return pad.edges(selectors.NearestToPointSelector(corner)).chamfer(c)


def build_thermal_pad(params: ThermalPadParams) -> cq.Workplane:
    pad = (
        cq.Workplane("XY")
        .box(params.thermal_pad_x, params.thermal_pad_y, params.thermal_pad_thickness)
        .translate((0, 0, params.thermal_pad_thickness / 2))
    )
    return _chamfer_pin1_pad_corner(
        pad,
        pad_x=params.thermal_pad_x,
        pad_y=params.thermal_pad_y,
        pad_thickness=params.thermal_pad_thickness,
        chamfer=params.thermal_pad_pin1_chamfer,
    )


def thermal_pad_solids(
    pad: ThermalPadSpec,
    *,
    layout: LeadLayout,
    lead_width: float,
    grounded_indices: set[int],
) -> list[tuple[str, cq.Workplane]]:
    pad_solid = (
        cq.Workplane("XY")
        .box(pad.x, pad.y, pad.thickness)
        .translate((0, 0, pad.thickness / 2))
    )
    solids: list[tuple[str, cq.Workplane]] = [("thermal_pad", pad_solid)]
    strip_length = pad.td_center_strip
    if strip_length <= 0:
        return solids
    if len(grounded_indices) < 2:
        return solids
    td_positions = positions(layout.leads_per_td_side, layout.pitch)
    grounded_positions = [td_positions[idx - 1] for idx in sorted(grounded_indices)]
    inner_pair = sorted(sorted(grounded_positions, key=abs)[:2])
    left_center, right_center = inner_pair
    x_min = left_center + lead_width / 2
    x_max = right_center - lead_width / 2
    strip_width = x_max - x_min
    if strip_width <= 0:
        return solids
    strip_center_x = (x_min + x_max) / 2
    z_center = pad.thickness / 2
    y_top = pad.y / 2 + strip_length / 2
    y_bottom = -pad.y / 2 - strip_length / 2
    strip_profile = cq.Workplane("XY").box(strip_width, strip_length, pad.thickness)
    strip_top = strip_profile.translate((strip_center_x, y_top, z_center))
    strip_bottom = strip_profile.translate((strip_center_x, y_bottom, z_center))
    solids.append(("thermal_pad_strip_top", strip_top))
    solids.append(("thermal_pad_strip_bottom", strip_bottom))
    return solids


def thermal_pad_solids_for_params(
    params: ThermalPadStripParams,
    *,
    layout: LeadLayout,
    lead_width: float,
    grounded_indices: set[int],
) -> list[tuple[str, cq.Workplane]]:
    pad_spec = ThermalPadSpec(
        x=params.thermal_pad_x,
        y=params.thermal_pad_y,
        thickness=params.thermal_pad_thickness,
        td_center_strip=params.thermal_pad_td_center_strip,
    )
    solids: list[tuple[str, cq.Workplane]] = []
    for name, solid in thermal_pad_solids(
        pad_spec,
        layout=layout,
        lead_width=lead_width,
        grounded_indices=grounded_indices,
    ):
        if name == "thermal_pad":
            solid = _chamfer_pin1_pad_corner(
                solid,
                pad_x=params.thermal_pad_x,
                pad_y=params.thermal_pad_y,
                pad_thickness=params.thermal_pad_thickness,
                chamfer=params.thermal_pad_pin1_chamfer,
            )
        solids.append((name, solid))
    return solids
