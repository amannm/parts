from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cadquery as cq
from cadquery.occ_impl.exporters import assembly as asm_export


@dataclass(frozen=True)
class ChipAntennaParams:
    """Chip antenna package parameters.

    Default values based on AANI-CH-0070 2.4GHz Loop Chip Antenna.
    All dimensions in millimeters.
    """

    # Package outline
    body_x: float = 1.0  # Length (1.00 ± 0.10)
    body_y: float = 0.5  # Width (0.50 ± 0.10)
    body_height: float = 0.4  # Height (0.40 ± 0.05)

    # Pad dimensions (4 corner pads)
    pad_length: float = 0.25  # Along X axis (0.25 +0.10/-0.05)
    pad_width: float = 0.15  # Along Y axis (0.15 +0.10/-0.05)
    pad_thickness: float = 0.01  # Z height
    pad_setback_x: float = 0.08  # Setback from X edges (0.08 +0.10/-0.05)

    # Pin 1 marker
    pin1_marker_size: float = 0.1
    pin1_marker_depth: float = 0.05


def _build_body(params: ChipAntennaParams) -> cq.Workplane:
    """Build the main package body (ceramic)."""
    body = (
        cq.Workplane("XY")
        .box(params.body_x, params.body_y, params.body_height)
        .edges("|Z")
        .fillet(0.025)
        .translate((0, 0, params.body_height / 2))
    )
    return body


def _build_pin1_marker(params: ChipAntennaParams) -> cq.Workplane:
    """Build the pin 1 indicator (small square depression on top surface)."""
    # Position marker near corner 1 (bottom-left in top view, which is -X, -Y)
    marker_x = -params.body_x / 2 + params.pad_length / 2 + 0.05
    marker_y = -params.body_y / 2 + params.pad_width / 2 + 0.05
    marker_z = params.body_height

    marker = (
        cq.Workplane("XY")
        .workplane(offset=marker_z)
        .moveTo(marker_x, marker_y)
        .rect(params.pin1_marker_size, params.pin1_marker_size)
        .extrude(-params.pin1_marker_depth)
    )
    return marker


def _build_pad(
    params: ChipAntennaParams, x_offset: float, y_offset: float
) -> cq.Workplane:
    """Build a single corner pad."""
    pad = (
        cq.Workplane("XY")
        .box(params.pad_length, params.pad_width, params.pad_thickness)
        .translate((x_offset, y_offset, -params.pad_thickness / 2))
    )
    return pad


def _build_pads(params: ChipAntennaParams) -> list[tuple[str, cq.Workplane]]:
    """Build all 4 corner pads.

    Pin layout (top view):
        4 (FEED) ---- 3 (GND)
           |            |
        1 (FEED) ---- 2 (GND)
    """
    pads = []

    # Pads: setback from X edges, flush with Y edges
    x_offset = params.body_x / 2 - params.pad_setback_x - params.pad_length / 2
    y_offset = params.body_y / 2 - params.pad_width / 2

    # Pin 1: bottom-left (-X, -Y) - FEED
    pads.append(("pin1_feed", _build_pad(params, -x_offset, -y_offset)))

    # Pin 2: bottom-right (+X, -Y) - GND
    pads.append(("pin2_gnd", _build_pad(params, x_offset, -y_offset)))

    # Pin 3: top-right (+X, +Y) - GND
    pads.append(("pin3_gnd", _build_pad(params, x_offset, y_offset)))

    # Pin 4: top-left (-X, +Y) - FEED
    pads.append(("pin4_feed", _build_pad(params, -x_offset, y_offset)))

    return pads


def build_model(params: ChipAntennaParams | None = None) -> cq.Workplane:
    """Build a unified chip antenna model.

    Args:
        params: Chip antenna parameters. Defaults to AANI-CH-0070.

    Returns:
        CadQuery Workplane with the complete model.
    """
    if params is None:
        params = ChipAntennaParams()

    body = _build_body(params)

    # Add pin 1 marker (cut into body)
    pin1_marker = _build_pin1_marker(params)
    body = body.cut(pin1_marker)

    model = body

    # Add pads
    pads = _build_pads(params)
    for _, pad in pads:
        model = model.union(pad)

    return model


def build_assembly(params: ChipAntennaParams | None = None) -> cq.Assembly:
    """Build a chip antenna as an assembly with named components.

    Args:
        params: Chip antenna parameters. Defaults to AANI-CH-0070.

    Returns:
        CadQuery Assembly with body and pads as separate components.
    """
    if params is None:
        params = ChipAntennaParams()

    assembly = cq.Assembly()

    body = _build_body(params)
    pin1_marker = _build_pin1_marker(params)
    body = body.cut(pin1_marker)

    assembly.add(body, name="body")

    pads = _build_pads(params)
    for name, pad in pads:
        assembly.add(pad, name=name)

    return assembly


def export_step(model: cq.Workplane | cq.Assembly, out_path: Path) -> None:
    """Export a model or assembly to STEP format."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(model, cq.Assembly):
        asm_export.exportAssembly(model, str(out_path))
    else:
        cq.exporters.export(model, str(out_path))


# Predefined configuration
AANI_CH_0070 = ChipAntennaParams()


if __name__ == "__main__":
    from cadquery.vis import show

    params = AANI_CH_0070
    result = build_assembly(params)
    export_step(result, Path("aani_ch_0070.step"))
    show(result, width=1280, height=720, zoom=0, roll=0, elevation=0, interact=True)
