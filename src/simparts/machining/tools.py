from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping


ToolKind = Literal[
    "generic",
    "end_mill",
    "ball_end_mill",
    "drill",
    "boring_bar",
    "reamer",
    "chamfer_mill",
    "thread_mill",
    "form_tool",
    "lathe_tool",
    "wire_form_tool",
    "probe",
]


@dataclass(frozen=True)
class Tool:
    """A virtual cutter or forming tool used by a machining operation.

    The tool is process metadata, not the cutter solid itself. CadQuery still
    receives explicit cutter geometry from an operation; this object records
    what kind of CNC tool would plausibly create that geometry.
    """

    name: str
    diameter: float | None = None
    number: int | None = None
    kind: ToolKind = "generic"
    corner_radius: float = 0.0
    flute_length: float | None = None
    included_angle_deg: float | None = None
    units: str = "mm"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.diameter is not None and self.diameter <= 0:
            raise ValueError("Tool diameter must be positive.")
        if self.corner_radius < 0:
            raise ValueError("Tool corner radius must be non-negative.")
        if self.flute_length is not None and self.flute_length <= 0:
            raise ValueError("Tool flute length must be positive.")
        if self.included_angle_deg is not None and self.included_angle_deg <= 0:
            raise ValueError("Tool included angle must be positive.")

    @property
    def tool_code(self) -> str | None:
        if self.number is None:
            return None
        return f"T{self.number}"

    def label(self) -> str:
        if self.tool_code is None:
            return self.name
        return f"{self.tool_code} {self.name}"

    def comment(self) -> str:
        fields = [self.label(), self.kind]
        if self.diameter is not None:
            fields.append(f"D={self.diameter:g}{self.units}")
        if self.corner_radius:
            fields.append(f"R={self.corner_radius:g}{self.units}")
        if self.included_angle_deg is not None:
            fields.append(f"A={self.included_angle_deg:g}deg")
        return ", ".join(fields)


@dataclass(frozen=True)
class EndMill(Tool):
    kind: ToolKind = "end_mill"


@dataclass(frozen=True)
class BallEndMill(Tool):
    kind: ToolKind = "ball_end_mill"


@dataclass(frozen=True)
class Drill(Tool):
    kind: ToolKind = "drill"


@dataclass(frozen=True)
class BoringBar(Tool):
    kind: ToolKind = "boring_bar"


@dataclass(frozen=True)
class Reamer(Tool):
    kind: ToolKind = "reamer"


@dataclass(frozen=True)
class ChamferMill(Tool):
    kind: ToolKind = "chamfer_mill"


@dataclass(frozen=True)
class ThreadMill(Tool):
    kind: ToolKind = "thread_mill"


@dataclass(frozen=True)
class FormTool(Tool):
    kind: ToolKind = "form_tool"


@dataclass(frozen=True)
class LatheTool(Tool):
    kind: ToolKind = "lathe_tool"


@dataclass(frozen=True)
class WireFormTool(Tool):
    kind: ToolKind = "wire_form_tool"
