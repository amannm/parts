from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import cadquery as cq
from cadquery.occ_impl.exporters import assembly as asm_export
from cadquery.vis import show


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


def _grounded_td_indices(params: RGY0020DParams) -> set[int]:
    grounded_count = max(
        0, min(params.leads_grounded_per_td_side, params.leads_per_td_side)
    )
    grounded_start = (params.leads_per_td_side - grounded_count) // 2
    return set(range(grounded_start + 1, grounded_start + grounded_count + 1))


def _lead_instances(params: RGY0020DParams, prefix: str = "lead", with_dimple: bool = False) -> list[tuple[str, cq.Workplane]]:
    def apply_dimple(lead: cq.Workplane, length: float) -> cq.Workplane:
        if not with_dimple:
            return lead
        return lead.cut(
            _lead_dimple_cut(
                params.dimple_width,
                params.dimple_height,
                params.dimple_depth,
                -length / 2,
            )
        )

    def make_rounded_lead(length: float) -> cq.Workplane:
        return apply_dimple(
            _rounded_lead(length, params.lead_width, params.lead_height), length
        )

    def make_flat_lead(length: float) -> cq.Workplane:
        lead = cq.Workplane("XY").box(
            length,
            params.lead_width,
            params.lead_height,
            centered=(True, True, False),
        )
        return apply_dimple(lead, length)

    base_lead = make_rounded_lead(params.lead_length)
    leads: list[tuple[str, cq.Workplane]] = []
    lr_positions = _positions(params.leads_per_lr_side, params.lead_pitch)
    x_left = -params.body_x / 2 + params.lead_setback + params.lead_length / 2
    x_right = params.body_x / 2 - params.lead_setback - params.lead_length / 2
    for idx, y in enumerate(lr_positions, start=1):
        left = base_lead.translate((x_left, y, 0))
        right = base_lead.rotate((0, 0, 0), (0, 0, 1), 180).translate((x_right, y, 0))
        leads.append((f"{prefix}_L{idx}", left))
        leads.append((f"{prefix}_R{idx}", right))
    grounded_indices = _grounded_td_indices(params)
    if grounded_indices:
        target_length = (
                (params.body_y / 2 - params.lead_setback) - (params.thermal_pad_y / 2)
        )
        grounded_length = target_length
        grounded_lead = make_flat_lead(grounded_length)
    else:
        grounded_length = params.lead_length
        grounded_lead = base_lead
    td_positions = _positions(params.leads_per_td_side, params.lead_pitch)
    for idx, x in enumerate(td_positions, start=1):
        use_grounded = idx in grounded_indices
        lead = grounded_lead if use_grounded else base_lead
        length = grounded_length if use_grounded else params.lead_length
        y_top = params.body_y / 2 - params.lead_setback - length / 2
        y_bottom = -params.body_y / 2 + params.lead_setback + length / 2
        top = lead.rotate((0, 0, 0), (0, 0, 1), -90).translate((x, y_top, 0))
        bottom = lead.rotate((0, 0, 0), (0, 0, 1), 90).translate((x, y_bottom, 0))
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
    return body


def _thermal_pad_solids(params: RGY0020DParams) -> list[tuple[str, cq.Workplane]]:
    pad = (
        cq.Workplane("XY")
        .box(params.thermal_pad_x, params.thermal_pad_y, params.thermal_pad_thickness)
        .translate((0, 0, params.thermal_pad_thickness / 2))
    )
    solids: list[tuple[str, cq.Workplane]] = [("thermal_pad", pad)]
    strip_length = params.thermal_pad_td_center_strip
    if strip_length <= 0:
        return solids
    grounded_indices = _grounded_td_indices(params)
    if len(grounded_indices) < 2:
        return solids
    td_positions = _positions(params.leads_per_td_side, params.lead_pitch)
    grounded_positions = [td_positions[idx - 1] for idx in sorted(grounded_indices)]
    inner_pair = sorted(sorted(grounded_positions, key=abs)[:2])
    left_center, right_center = inner_pair
    x_min = left_center + params.lead_width / 2
    x_max = right_center - params.lead_width / 2
    strip_width = x_max - x_min
    if strip_width <= 0:
        return solids
    strip_center_x = (x_min + x_max) / 2
    z_center = params.thermal_pad_thickness / 2
    y_top = params.thermal_pad_y / 2 + strip_length / 2
    y_bottom = -params.thermal_pad_y / 2 - strip_length / 2
    strip_profile = cq.Workplane("XY").box(
        strip_width, strip_length, params.thermal_pad_thickness
    )
    strip_top = strip_profile.translate((strip_center_x, y_top, z_center))
    strip_bottom = strip_profile.translate((strip_center_x, y_bottom, z_center))
    solids.append(("thermal_pad_strip_top", strip_top))
    solids.append(("thermal_pad_strip_bottom", strip_bottom))
    return solids


def _union_solids(solids: list[cq.Workplane]) -> cq.Workplane | None:
    result = None
    for solid in solids:
        result = solid if result is None else result.union(solid)
    return result


def build_model(params: RGY0020DParams) -> cq.Workplane:
    body = _build_body(params)

    leads_for_cut = _lead_instances(params, prefix="cut", with_dimple=False)
    leads = _lead_instances(params, with_dimple=True)
    for _, lead in leads_for_cut:
        body = body.cut(lead)

    model = body
    for _, lead in leads:
        model = model.union(lead)

    for _, solid in _thermal_pad_solids(params):
        model = model.union(solid)

    return model


def build_assembly(params: RGY0020DParams) -> cq.Assembly:
    assembly = cq.Assembly()
    body = _build_body(params)
    leads_for_cut = _lead_instances(params, prefix="cut", with_dimple=False)
    leads = _lead_instances(params, with_dimple=True)
    for _, lead in leads_for_cut:
        body = body.cut(lead)
    assembly.add(body, name="body")
    grounded_indices = _grounded_td_indices(params)
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

    pad_union = _union_solids([solid for _, solid in _thermal_pad_solids(params)])
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
    # TODO: take snapshots of the top, bottom, side views of chip
    show(result, width=1280, height=720, zoom=0, roll=0, elevation=0, interact=True)
