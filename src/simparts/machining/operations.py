from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from simparts.machining.gcode import ToolPath
from simparts.machining.tools import Tool


OperationKind = Literal[
    "setup",
    "rough_mill",
    "profile_mill",
    "pocket_mill",
    "drill",
    "bore",
    "ream",
    "turn",
    "groove",
    "thread",
    "form_cut",
    "sweep_cut",
    "finish",
    "wire_form",
    "insert",
    "custom",
]

MaterialAction = Literal["none", "cut", "add", "replace", "finish"]


def _comment(text: str) -> str:
    return f"({text.replace(')', ']')})"


@dataclass(frozen=True)
class OperationRecord:
    name: str
    kind: OperationKind
    action: MaterialAction = "none"
    tool: Tool | None = None
    strategy: str = ""
    parameters: Mapping[str, Any] = field(default_factory=dict)
    toolpath: ToolPath | None = None
    work_offset: str = "G54"
    spindle_rpm: float | None = None
    feed: float | None = None
    coolant: bool = False
    tags: tuple[str, ...] = ()

    def summary(self) -> str:
        parts = [self.kind, self.action]
        if self.tool is not None:
            parts.append(self.tool.label())
        if self.strategy:
            parts.append(self.strategy)
        return " | ".join(parts)

    def to_gcode(self) -> list[str]:
        lines = [_comment(f"OP {self.name}: {self.summary()}")]
        if self.parameters:
            params = ", ".join(f"{key}={value}" for key, value in sorted(self.parameters.items()))
            lines.append(_comment(params))
        if self.tool is not None:
            if self.tool.number is not None:
                lines.append(f"T{self.tool.number} M6")
            lines.append(_comment(f"TOOL {self.tool.comment()}"))
        lines.append(self.work_offset)
        if self.spindle_rpm is not None:
            lines.append(f"S{self.spindle_rpm:.6g} M3")
        if self.coolant:
            lines.append("M8")
        if self.feed is not None:
            lines.append(f"F{self.feed:.6g}")
        if self.toolpath is None:
            lines.append(_comment("CadQuery volume operation; attach ToolPath for explicit G-code moves"))
        else:
            lines.extend(self.toolpath.to_gcode())
        if self.coolant:
            lines.append("M9")
        if self.spindle_rpm is not None:
            lines.append("M5")
        return lines


@dataclass(frozen=True)
class MachiningPlan:
    operations: tuple[OperationRecord, ...] = ()

    def append(self, operation: OperationRecord) -> MachiningPlan:
        return MachiningPlan(self.operations + (operation,))

    def to_gcode(self, *, program_name: str = "SIMPART") -> str:
        lines = [
            "%",
            _comment(f"PROGRAM {program_name}"),
            "G90",
            "G21",
        ]
        for operation in self.operations:
            lines.extend(operation.to_gcode())
        lines.extend(["M30", "%"])
        return "\n".join(lines)
