from __future__ import annotations

from dataclasses import dataclass, field, replace

import cadquery as cq

from simparts.machining.workpiece import Workpiece


def _comment(text: str) -> str:
    return f"({text.replace(')', ']')})"


@dataclass(frozen=True)
class MachinedComponent:
    name: str
    workpiece: Workpiece
    color: cq.Color | None = None
    loc: cq.Location | None = None


@dataclass(frozen=True)
class MachinedAssembly:
    """A CadQuery assembly whose components retain individual process plans."""

    name: str = "machined_assembly"
    components: tuple[MachinedComponent, ...] = field(default_factory=tuple)

    def add(
        self,
        workpiece: Workpiece,
        *,
        name: str | None = None,
        color: cq.Color | None = None,
        loc: cq.Location | None = None,
    ) -> MachinedAssembly:
        component = MachinedComponent(
            name=name or workpiece.name,
            workpiece=workpiece,
            color=color,
            loc=loc,
        )
        return replace(self, components=self.components + (component,))

    def to_cadquery(self) -> cq.Assembly:
        assembly = cq.Assembly()
        for component in self.components:
            assembly.add(
                component.workpiece.as_workplane(),
                name=component.name,
                color=component.color,
                loc=component.loc,
            )
        return assembly

    def to_gcode(self) -> str:
        lines = ["%", _comment(f"ASSEMBLY {self.name}"), "G90", "G21"]
        for component in self.components:
            lines.append(_comment(f"COMPONENT {component.name}"))
            for operation in component.workpiece.plan.operations:
                lines.extend(operation.to_gcode())
        lines.extend(["M30", "%"])
        return "\n".join(lines)
