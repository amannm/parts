from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Literal

import cadquery as cq


@dataclass(frozen=True)
class LeadDims:
    length: float
    width: float
    height: float


@dataclass(frozen=True)
class LeadLayout:
    body_x: float
    body_y: float
    pitch: float
    setback: float = 0.0
    leads_per_lr_side: int = 0
    leads_per_td_side: int = 0


@dataclass(frozen=True)
class LeadDimple:
    width: float
    height: float
    depth: float


@dataclass(frozen=True)
class GroundedLeadSpec:
    count_per_td_side: int
    length: float | None = None
    profile: Literal["flat", "rounded", "chamfered"] = "flat"
    chamfer: float = 0.0


@dataclass(frozen=True)
class LeadSets:
    cuts: list[tuple[str, cq.Workplane]]
    leads: list[tuple[str, cq.Workplane]]


def positions(count: int, pitch: float) -> list[float]:
    if count <= 0:
        return []
    start = -0.5 * (count - 1) * pitch
    return [start + i * pitch for i in range(count)]


def rounded_lead(length: float, width: float, height: float) -> cq.Workplane:
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


def flat_lead(length: float, width: float, height: float) -> cq.Workplane:
    return cq.Workplane("XY").box(
        length,
        width,
        height,
        centered=(True, True, False),
    )


def chamfered_lead(
    length: float, width: float, height: float, chamfer: float
) -> cq.Workplane:
    half_w = width / 2.0
    half_l = length / 2.0
    max_chamfer = min(half_w, half_l) * 0.99
    c = min(chamfer, max_chamfer)
    if c <= 0:
        return flat_lead(length, width, height)
    profile = (
        cq.Workplane("XY")
        .rect(length, width)
        .extrude(height)
        .faces("<X")
        .edges("|Z")
        .chamfer(c, c/2)
    )
    return profile


def grounded_td_indices(leads_per_td_side: int, grounded_per_td_side: int) -> set[int]:
    grounded_count = max(0, min(grounded_per_td_side, leads_per_td_side))
    grounded_start = (leads_per_td_side - grounded_count) // 2
    return set(range(grounded_start + 1, grounded_start + grounded_count + 1))


def pin_dimple_cut(dimple: LeadDimple, pin_offset: float) -> cq.Workplane:
    radius = max(dimple.width, dimple.height, dimple.depth) / 2.0 - 0.000000001
    wp = (
        cq.Workplane("XY")
        .box(dimple.depth, dimple.width, dimple.height, centered=(False, True, False))
        .translate((pin_offset, 0, 0))
    )
    e_on_z = wp.faces(">Z").edges("|X or >X")
    e_on_x = wp.faces(">X").edges("|Z or >Z")
    return e_on_z.add(e_on_x).fillet(radius)


def _apply_dimple(
    lead: cq.Workplane,
    dimple: LeadDimple | None,
    pin_length: float,
) -> cq.Workplane:
    if dimple is None:
        return lead
    return lead.cut(pin_dimple_cut(dimple, -pin_length / 2))


def rectangular_pin_instances(
    layout: LeadLayout,
    lead: LeadDims,
    *,
    prefix: str = "lead",
    dimple: LeadDimple | None = None,
    grounded: GroundedLeadSpec | None = None,
    profile: Literal["flat", "rounded", "chamfered"] = "rounded",
    chamfer: float = 0.0,
) -> list[tuple[str, cq.Workplane]]:
    def make_lead(
        length: float,
        prof: Literal["flat", "rounded", "chamfered"],
        cham: float = 0.0,
    ) -> cq.Workplane:
        if prof == "flat":
            shape = flat_lead(length, lead.width, lead.height)
        elif prof == "rounded":
            shape = rounded_lead(length, lead.width, lead.height)
        elif prof == "chamfered":
            shape = chamfered_lead(length, lead.width, lead.height, cham)
        else:
            raise ValueError(f"Unsupported lead profile: {prof}")
        return _apply_dimple(shape, dimple, length)
    base_lead = make_lead(lead.length, profile, chamfer)
    leads: list[tuple[str, cq.Workplane]] = []
    lr_positions = positions(layout.leads_per_lr_side, layout.pitch)
    x_left = -layout.body_x / 2 + layout.setback + lead.length / 2
    x_right = layout.body_x / 2 - layout.setback - lead.length / 2
    for idx, y in enumerate(lr_positions, start=1):
        left = base_lead.translate((x_left, y, 0))
        right = base_lead.rotate((0, 0, 0), (0, 0, 1), 180).translate((x_right, y, 0))
        leads.append((f"{prefix}_L{idx}", left))
        leads.append((f"{prefix}_R{idx}", right))
    grounded_indices: set[int] = set()
    grounded_length = lead.length
    grounded_profile: Literal["flat", "rounded", "chamfered"] = profile
    grounded_chamfer = chamfer
    if grounded is not None:
        grounded_indices = grounded_td_indices(
            layout.leads_per_td_side, grounded.count_per_td_side
        )
        grounded_length = grounded.length if grounded.length is not None else lead.length
        grounded_profile = grounded.profile
        grounded_chamfer = grounded.chamfer if grounded.chamfer > 0 else chamfer
    grounded_lead = (
        make_lead(grounded_length, grounded_profile, grounded_chamfer)
        if grounded_indices
        else base_lead
    )
    td_positions = positions(layout.leads_per_td_side, layout.pitch)
    for idx, x in enumerate(td_positions, start=1):
        use_grounded = idx in grounded_indices
        pin_solid = grounded_lead if use_grounded else base_lead
        length = grounded_length if use_grounded else lead.length
        y_top = layout.body_y / 2 - layout.setback - length / 2
        y_bottom = -layout.body_y / 2 + layout.setback + length / 2
        top = pin_solid.rotate((0, 0, 0), (0, 0, 1), -90).translate((x, y_top, 0))
        bottom = pin_solid.rotate((0, 0, 0), (0, 0, 1), 90).translate((x, y_bottom, 0))
        leads.append((f"{prefix}_T{idx}", top))
        leads.append((f"{prefix}_B{idx}", bottom))
    return leads


def rectangular_pin_sets(
    layout: LeadLayout,
    lead: LeadDims,
    *,
    prefix: str = "lead",
    cut_prefix: str = "cut",
    dimple: LeadDimple | None = None,
    grounded: GroundedLeadSpec | None = None,
    profile: Literal["flat", "rounded", "chamfered"] = "rounded",
    chamfer: float = 0.0,
) -> LeadSets:
    pin_cuts = rectangular_pin_instances(
        layout,
        lead,
        prefix=cut_prefix,
        dimple=None,
        grounded=grounded,
        profile=profile,
        chamfer=chamfer,
    )
    pin_solids = rectangular_pin_instances(
        layout,
        lead,
        prefix=prefix,
        dimple=dimple,
        grounded=grounded,
        profile=profile,
        chamfer=chamfer,
    )
    return LeadSets(cuts=pin_cuts, leads=pin_solids)


def cut_body_for_leads(
    body: cq.Workplane,
    pin_cuts: Iterable[tuple[str, cq.Workplane]],
) -> cq.Workplane:
    for _, lead in pin_cuts:
        body = body.cut(lead)
    return body


def union_leads(
    model: cq.Workplane,
    leads: Iterable[tuple[str, cq.Workplane]],
) -> cq.Workplane:
    for _, lead in leads:
        model = model.union(lead)
    return model


def add_leads_to_assembly(
    assembly: cq.Assembly,
    leads: Iterable[tuple[str, cq.Workplane]],
) -> None:
    for name, lead in leads:
        assembly.add(lead, name=name)


_TD_NAME_RE = re.compile(r".*_[TB](\d+)$")


def td_index_from_name(name: str) -> int | None:
    match = _TD_NAME_RE.match(name)
    if not match:
        return None
    return int(match.group(1))


def split_grounded_td_leads(
    leads: Iterable[tuple[str, cq.Workplane]],
    grounded_indices: set[int],
) -> tuple[list[tuple[str, cq.Workplane]], list[tuple[str, cq.Workplane]]]:
    grounded: list[tuple[str, cq.Workplane]] = []
    ungrounded: list[tuple[str, cq.Workplane]] = []
    for name, lead in leads:
        td_index = td_index_from_name(name)
        if td_index in grounded_indices:
            grounded.append((name, lead))
        else:
            ungrounded.append((name, lead))
    return grounded, ungrounded
