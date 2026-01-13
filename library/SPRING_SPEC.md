I’ll outline a comprehensive variable checklist for fully defining a spring’s geometry across the most common spring types (compression/extension, torsion, conical/barrel, wave, and flat/spiral), plus the derived geometric quantities that are often treated as inputs in CAD/analysis.


Below is a practical “input variable” checklist that, taken together, can fully specify **spring geometry**. Because “mechanical spring” can mean several families, I’m grouping by the most common types and calling out shared/core variables first.

## A) Helical wire springs (compression / extension) — most common

### 1) Wire cross-section (defines the body being wound)

* **Wire diameter,** (d) (round wire), *or* for non-round:
* **Wire width,** (b) and **wire thickness,** (t) (rectangular)
* **Cross-section shape descriptor** (round / square / rectangular / custom)
* **Edge radii / corner radius** (for rectangular/square wire, if modeled)

### 2) Coil size (centerline geometry)

Pick one equivalent set (CAD tools vary):

* **Mean coil diameter,** (D_m)
  *or* **Outer diameter,** (D_o)
  *or* **Inner diameter,** (D_i)
  (with (D_o = D_m + d), (D_i = D_m - d) for round wire)

### 3) Helix progression (axial geometry)

* **Pitch,** (p) (axial advance per turn)
  *or* **Helix angle** (at mean diameter)
  *or* **Free length,** (L_f) (combined with turn count below)

### 4) Turn/coil count (how many wraps)

* **Total coils/turns,** (N_t)
* **Active coils,** (N_a) (if end coils are inactive)
* **End coils,** (N_e = N_t - N_a) (if modeled explicitly)

### 5) End geometry (this is where “fully specify” usually fails)

For **compression springs**:

* **End type** (plain, plain & ground, squared/closed, squared & ground, etc.)
* **Number of closed (dead) end turns** (if “squared/closed”)
* **Grounding parameters** (ground length/extent, ground angle / grind flat depth)
* **End transition geometry** (how the pitch ramps into the end: linear ramp length, etc.)
* **End clocking / rotational orientation** (angle locating the end relative to a datum)

For **extension springs** (in addition to body above):

* **Hook/loop type** (machine hook, crossover center, side hook, threaded insert, etc.)
* For each end fitting:

  * **Hook inside/mean diameter** (or hook radius)
  * **Hook opening / gap**
  * **Hook length / leg length**
  * **Hook bend radius**
  * **Hook plane / orientation** (in-plane / out-of-plane)
  * **Hook angle (clocking)** relative to body and relative to other end
* **Body initial tension geometry surrogate** (often represented geometrically by how tight the body coils are: e.g., pitch at rest ≈ 0, coil-to-coil contact definition)

### 6) Handedness and reference

* **Helix handedness** (right-hand / left-hand)
* **Reference axis and datum origin** (CAD positioning variable, but required for “fully specify” in an assembly)

---

## B) Helical torsion springs (wire wound, torque springs)

You still need all “helical body” variables above **except** free length is less central; instead you must define arms/legs.

### 1) Body

* (d) (or (b,t)), (D_m) (or (D_o/D_i)), (N_t), pitch/helix progression (often near-zero)
* **Coil direction/handedness**

### 2) Legs/arms (dominant geometric inputs)

For **each leg**:

* **Leg type** (straight tangent, radial, axial, custom form)
* **Leg length** (from tangent point)
* **Leg bend angle(s)** / **included angle** between legs
* **Leg plane** (in-plane vs out-of-plane)
* **Leg bend radius**
* **Leg end feature** (hook, notch, tang, etc.)
* **Leg clocking** relative to coil (start angle)

Optional but common:

* **Body-to-leg transition length** / **pitch ramp near legs**

---

## C) Variable-diameter helical springs (conical, barrel, hourglass)

Start with **wire + turn count**, then add the diameter law.

* **Small end mean diameter,** (D_{m,1}) (or (D_{o,1}))
* **Large end mean diameter,** (D_{m,2}) (or (D_{o,2}))
* **Free length,** (L_f)
* **Total turns,** (N_t) (and active turns)
* **Diameter variation profile** along turns (linear taper, parabolic/barrel profile, custom)
* **Pitch distribution** (constant pitch vs variable pitch; specify pitch at ends and/or a pitch function)
* **End types** (as in compression springs) and **end clocking**

For conical specifically, you can also use:

* **Cone angle** (instead of both end diameters)

---

## D) Wave springs / crest-to-crest washers (if that’s what you mean)

Wave springs are defined more by rings and waves than helical parameters:

* **Mean diameter** (or inner/outer diameter)
* **Radial width** (OD–ID relationship)
* **Material thickness**
* **Number of waves (lobes)**
* **Wave amplitude / wave height**
* **Wave form** (sinusoidal, trapezoidal, custom)
* **Number of turns** (single-turn, multi-turn wave spring)
* **End overlap/step geometry** (for multi-turn)
* **Edge conditions** (chamfer/radius)

---

## E) Flat/spiral (clock) springs (strip wound in a plane)

* **Strip thickness,** (t)
* **Strip width,** (b)
* **Spiral law** (Archimedean spiral parameter(s) or inner radius + pitch)
* **Inner coil radius/diameter**
* **Outer coil radius/diameter**
* **Number of turns** (or strip length)
* **Inner attachment geometry** (hole, hook, arbor shape, slot)
* **Outer attachment geometry** (hole/hook/tab)
* **Handedness** (wind direction)
* **Clearances/gaps** (if not in contact)

---

## “Derived but often treated as inputs” (common in CAD/specs)

These aren’t strictly independent, but many workflows accept them as “inputs” and solve others:

* **Spring index** (C = D_m/d)
* **Solid height** (H_s) (compression; depends on coil count + wire size + end style)
* **Coil-to-coil gap** (free state)
* **Body length** (length excluding hooks/legs for extension/torsion)
* **Overall envelope** (bounding OD/ID and overall length including hooks/legs)

---

### If you want the shortest “fully specifying” set for a *standard cylindrical compression spring*

A minimal independent set that usually fully defines geometry is:

* Wire diameter (d)
* Mean diameter (D_m) (or OD/ID)
* Total coils (N_t) (and/or active coils (N_a))
* Free length (L_f) (or pitch (p))
* End type + (if needed) number of closed end coils
* Handedness + end clocking (if assembly orientation matters)

If you tell me which spring family you mean (compression vs extension vs torsion vs conical vs wave vs flat spiral), I can collapse this into a single clean “required inputs” list for that type only.
