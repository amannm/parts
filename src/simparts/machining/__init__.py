"""CadQuery-backed virtual machining primitives for parametric parts.

The framework records parts as workpieces acted on by virtual CNC operations:
stock is loaded, cutter envelopes remove material, prepared inserts add
material, and finishing passes annotate edge treatment.  Each operation stores
the virtual tool and a G-code-oriented process record while CadQuery performs
the exact solid modeling.

This operation vocabulary is intentionally broad enough for the current
``simparts.features`` package:

- rings, shafts, seals, and rotor/stator laminations use tube/cylinder stock,
  bore/profile cuts, toroidal form cuts, chamfering, and repeated slot cuts;
- balls, leads, pads, magnets, and PCB layers are prepared stocks inserted or
  joined into an assembly-level workpiece;
- gears use profiled or helical profile operations plus bore and finish passes;
- threads, springs, and turbine blades use swept cutter/forming envelopes where
  the path/profile math remains domain-specific but the process is still
  represented as a CNC-mappable operation.
"""

from simparts.machining.assembly import MachinedAssembly, MachinedComponent
from simparts.machining.gcode import Move, ToolPath
from simparts.machining.operations import MachiningPlan, OperationRecord
from simparts.machining.primitives import (
    Axis,
    Plane,
    VectorLike,
    box,
    circular_pattern,
    cylinder,
    extruded_profile,
    sphere,
    swept_profile,
    torus,
    tube,
    union_all,
)
from simparts.machining.tools import (
    BallEndMill,
    BoringBar,
    ChamferMill,
    Drill,
    EndMill,
    FormTool,
    LatheTool,
    Reamer,
    ThreadMill,
    Tool,
    ToolKind,
    WireFormTool,
)
from simparts.machining.workpiece import Workpiece

__all__ = [
    "Axis",
    "BallEndMill",
    "BoringBar",
    "ChamferMill",
    "Drill",
    "EndMill",
    "FormTool",
    "LatheTool",
    "MachinedAssembly",
    "MachinedComponent",
    "MachiningPlan",
    "Move",
    "OperationRecord",
    "Plane",
    "Reamer",
    "ThreadMill",
    "Tool",
    "ToolKind",
    "ToolPath",
    "VectorLike",
    "WireFormTool",
    "Workpiece",
    "box",
    "circular_pattern",
    "cylinder",
    "extruded_profile",
    "sphere",
    "swept_profile",
    "torus",
    "tube",
    "union_all",
]
