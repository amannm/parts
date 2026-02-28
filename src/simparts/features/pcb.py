from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

import cadquery as cq

from simparts.features.package import union_solids


LayerKind = Literal["core", "prepreg", "copper"]


@dataclass(frozen=True)
class PcbLayerSpec:
    kind: LayerKind
    thickness: float
    name: str | None = None


@dataclass(frozen=True)
class PcbStackup:
    x: float
    y: float
    layers: Sequence[PcbLayerSpec]
    solder_mask_thickness: float = 0.02
    solder_mask_oversize: float = 0.0


def _validate_stackup(stackup: PcbStackup) -> list[PcbLayerSpec]:
    if stackup.x <= 0 or stackup.y <= 0:
        raise ValueError("PCB dimensions must be positive.")
    layers = list(stackup.layers)
    if not layers:
        raise ValueError("PCB stackup must include at least one layer.")
    for idx, layer in enumerate(layers, start=1):
        if layer.thickness <= 0:
            raise ValueError(f"Layer {idx} thickness must be positive.")
    if stackup.solder_mask_thickness <= 0:
        raise ValueError("Solder mask thickness must be positive.")
    if stackup.solder_mask_oversize < 0:
        raise ValueError("Solder mask oversize must be non-negative.")
    copper_indices = [idx for idx, layer in enumerate(layers) if layer.kind == "copper"]
    if len(copper_indices) < 2:
        raise ValueError("PCB stackup must include at least two copper layers.")
    if layers[0].kind != "copper" or layers[-1].kind != "copper":
        raise ValueError("PCB stackup must start and end with copper layers.")
    return layers


def pcb_layer_solids(
    stackup: PcbStackup,
    *,
    origin: Literal["bottom", "center", "top"] = "bottom",
) -> list[tuple[str, cq.Workplane]]:
    """
    Build individual solids for each stackup layer plus top/bottom solder mask.

    Layer order is interpreted from bottom to top. Origin controls where z=0 is
    placed for the full stack including solder mask.
    """
    layers = _validate_stackup(stackup)
    z_cursor = 0.0
    placements: list[tuple[PcbLayerSpec, float, float]] = []
    for layer in layers:
        z0 = z_cursor
        z1 = z0 + layer.thickness
        placements.append((layer, z0, z1))
        z_cursor = z1

    copper_indices = [idx for idx, layer in enumerate(layers) if layer.kind == "copper"]
    bottom_copper = placements[copper_indices[0]]
    top_copper = placements[copper_indices[-1]]
    bottom_copper_z0 = bottom_copper[1]
    top_copper_z1 = top_copper[2]

    bottom_mask_z0 = bottom_copper_z0 - stackup.solder_mask_thickness
    bottom_mask_z1 = bottom_copper_z0
    top_mask_z0 = top_copper_z1
    top_mask_z1 = top_copper_z1 + stackup.solder_mask_thickness

    min_z = min(0.0, bottom_mask_z0)
    max_z = max(z_cursor, top_mask_z1)

    if origin == "bottom":
        offset = -min_z
    elif origin == "center":
        offset = -(min_z + max_z) / 2
    elif origin == "top":
        offset = -max_z
    else:
        raise ValueError(f"Unsupported origin: {origin}")

    counters = {"core": 0, "prepreg": 0, "copper": 0}
    solids: list[tuple[str, cq.Workplane]] = []
    for layer, z0, z1 in placements:
        counters[layer.kind] += 1
        name = layer.name or f"{layer.kind}_{counters[layer.kind]}"
        z_center = (z0 + z1) / 2 + offset
        solid = (
            cq.Workplane("XY")
            .box(stackup.x, stackup.y, layer.thickness)
            .translate((0, 0, z_center))
        )
        solids.append((name, solid))

    mask_x = stackup.x + 2 * stackup.solder_mask_oversize
    mask_y = stackup.y + 2 * stackup.solder_mask_oversize
    for name, z0, z1 in (
        ("solder_mask_bottom", bottom_mask_z0, bottom_mask_z1),
        ("solder_mask_top", top_mask_z0, top_mask_z1),
    ):
        z_center = (z0 + z1) / 2 + offset
        solid = (
            cq.Workplane("XY")
            .box(mask_x, mask_y, stackup.solder_mask_thickness)
            .translate((0, 0, z_center))
        )
        solids.append((name, solid))

    return solids


def build_pcb(stackup: PcbStackup, *, origin: Literal["bottom", "center", "top"] = "bottom") -> cq.Workplane:
    solids = [solid for _, solid in pcb_layer_solids(stackup, origin=origin)]
    result = union_solids(solids)
    if result is None:
        raise ValueError("PCB stackup produced no solids.")
    return result


def build_pcb_assembly(
    stackup: PcbStackup, *, origin: Literal["bottom", "center", "top"] = "bottom"
) -> cq.Assembly:
    assembly = cq.Assembly()
    for name, solid in pcb_layer_solids(stackup, origin=origin):
        assembly.add(solid, name=name)
    return assembly
