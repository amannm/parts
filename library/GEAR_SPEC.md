I’ll enumerate the geometric parameters typically used to define a standard involute gear (spur and helical), grouping them into tooth geometry, diameters, helix/lead, and tolerances so you have a complete checklist.


Below is a practical “complete checklist” of the **geometrical parameters used to fully specify a standard involute gear**. (Standards differ slightly by region—ISO vs AGMA—but these cover what you normally need to define the geometry unambiguously.)

## 1) Basic size and tooth count

* **Number of teeth,** *z*
* **Normal module** *mₙ* (metric) **or** **diametral pitch** *P* (inch)
* **Base pitch** (often derived) *p_b*
* **Circular pitch** (often derived) *p*

## 2) Pressure angle and tooth system

* **Pressure angle** *α* (transverse *α_t* and/or normal *αₙ* for helical)
* **Tooth profile type**: involute (standard), and **profile standard** / system (e.g., full-depth, stub)

## 3) Profile shift and tooth proportions

* **Profile shift coefficient** *x* (or *x₁, x₂* for a gear pair)
* **Addendum** *a* (often *a = m* times an addendum coefficient)
* **Dedendum** *b* (often *b = m* times a dedendum coefficient)
* **Whole depth** *h = a + b*
* **Working depth** *h_w*
* **Clearance** *c*
* **Fillet radius** at root *ρ_f* (or tool tip radius)

## 4) Reference, base, and working diameters (key circles)

(These are frequently *derived*, but many drawings/specs still call them out.)

* **Reference (pitch) diameter** *d*
* **Base diameter** *d_b*
* **Outside (addendum) diameter** *d_a*
* **Root (dedendum) diameter** *d_f*
* **Working pitch diameter** (for meshing pair) *d_w*
* **Tip/root circle radii** (if specified instead of diameters)

## 5) Tooth thickness / spacing specification

* **Tooth thickness at reference circle** *s* (or circular tooth thickness)
* **Space width** *e*
* **Measurement method + target value**, e.g.

  * **Base tangent length** / “span over k teeth” *W_k*
  * **Measurement over pins/balls** *M* (pin diameter included)
* **Backlash** (design backlash target; actual depends on tolerances)

## 6) Face and blank geometry (the gear “body”)

* **Face width** *b*
* **Gear blank / rim dimensions** (as needed for “fully specify”):

  * **Bore diameter**
  * **Hub diameter & length**
  * **Rim thickness**
  * **Web thickness**
  * **Keyway/spline geometry** (if applicable)
  * **Chamfers and edge breaks** (tip chamfer, corner radii)

## 7) Helical-specific parameters (omit for spur)

* **Helix angle** *β* (usually specified at reference cylinder)
* **Hand of helix** (LH / RH)
* **Lead** *L* (or **axial pitch** *p_x*)
* **Normal vs transverse quantities** explicitly (e.g., *mₙ* vs *m_t*, *αₙ* vs *α_t*)

## 8) Conjugate pair / meshing geometry (if you’re defining a gear pair)

(For a single gear alone, these aren’t strictly required—but they’re often part of a “gear specification.”)

* **Center distance** *a*
* **Operating pressure angle** *α_w*
* **Contact ratio** (transverse *ε_α*; overlap *ε_β* for helical)

## 9) Modifications (commonly required in real “standard” gear specs)

These are geometric changes to the ideal involute:

* **Profile modification (tip relief, root relief)**: amount and length
* **Lead/helix modification (crowning, end relief)**: amount and length
* **Tip chamfer / tip truncation**
* **Undercut allowance / tooth thinning** (if used)

## 10) Accuracy / geometry tolerances (not “shape” parameters, but required to fully define the manufactured geometry)

* **Quality/grade** (ISO or AGMA gear accuracy class)
* **Runout**, **pitch error**, **profile error**, **lead error**
* **Tooth-to-tooth variation**
* **Total composite error** (depending on inspection method)

---

### Minimal set (common “drawing-level” spec)

If you want the *smallest* set that still uniquely defines a typical involute gear tooth form (ignoring manufacturing tolerances and blank features), it’s usually:

* *z*, *m* (or *P*), *α*, **(β and hand if helical)**, *x* (if not zero), plus either **standard addendum/dedendum system** or explicit *d_a, d_f*, and **face width** *b*.

If you tell me **spur vs helical** and **ISO vs AGMA**, I can rewrite this as the exact parameter list in that standard’s preferred terms and symbols.
