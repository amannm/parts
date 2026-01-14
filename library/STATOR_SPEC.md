I’ll outline a comprehensive “parameter checklist” for fully defining a motor stator’s geometry (lamination stack + slots + winding window + end features), organized so you can directly turn it into CAD/FEA inputs.


Below is a practical “input variable checklist” that—taken together—fully specifies *stator geometry* for most radial-flux electric machines (IPM/SPM induction, SRM, etc.). I’m treating “stator” as: lamination cross-section + stack length/segmentation + slot/window features + (optional) end features that affect geometry.

I’ve grouped variables so you can lift them directly into CAD or FEA scripts.

---

## 1) Topology and counting variables

* **Machine type / slot style**: open / semi-closed / closed; distributed / concentrated; tooth-coil; segmented stator (yes/no)
* **Number of phases**: (m)
* **Number of stator slots**: (Q_s)
* **Number of pole pairs**: (p) (not stator-only, but needed to define periodicity/sector models)
* **Symmetry sector**: (N_{\text{sym}}) (e.g., gcd-based sector count)
* **Winding layers**: (N_{\text{layers}}) (1 or 2 typically)
* **Coil pitch / throw**: (y) (in slots) (needed if you want geometry of coil placement and end-turn mapping)

---

## 2) Global reference dimensions (2D cross-section)

These define the “envelope” the slots sit in.

* **Stator outer diameter**: (D_{so}) (or outer radius (R_{so}))
* **Stator inner diameter / bore**: (D_{si}) (or inner radius (R_{si}))
* **Airgap reference** (often rotor-defined, but for stator CAD you still need):

  * **Bore-to-airgap surface radius** (if you include slot opening fillets/bridges): (R_{ag}) (usually (R_{si}))
* **Reference axial datum / origin** (for downstream assembly): (x_0,y_0), orientation angle (\theta_0)

---

## 3) Back-iron (yoke) geometry

You can specify yoke either directly or derived from OD/slot depth.

* **Yoke thickness**: (t_y) (radial)
* **Yoke inner radius** (at slot bottom): (R_{y,i}) or **slot bottom radius** (R_{sb})
* **Yoke outer radius**: (R_{y,o}) (often (R_{so}))
* **Yoke fillet radii** at transitions: (r_{y,f}) (optional)

---

## 4) Slot/tooth layout (angular)

These set the slot pitch and how material is distributed around the circumference.

* **Slot pitch (mechanical)**: (\tau_s = 2\pi / Q_s)
* **Slot centerline reference**: (\theta_{\text{slot,0}})
* **Tooth tip arc / slot opening span**:

  * **Slot opening angle**: (\alpha_{so}) (at bore)
  * or **slot opening width**: (b_{so}) (linear at bore radius)
* **Tooth tip (shoe) angle**: (\alpha_{tt}) (if using a shoe)
* **Tooth width at bore**: (b_{t,i}) (or derived: (b_{t,i} = \tau_s R_{si} - b_{so}))

---

## 5) Slot shape variables (radial dimensions)

There are many slot families; the key is to parameterize each “station” along radius (opening → wedge/neck → body → bottom).

Common minimal set for a typical semi-closed slot:

**At bore / opening**

* **Slot opening width**: (b_{so})
* **Slot opening depth** (tip height): (h_{so})
* **Tooth-tip bridge thickness** (if closed): (t_{br}) (0 if open)
* **Slot mouth fillet radius**: (r_{so,f})

**Neck / wedge region (if present)**

* **Neck width**: (b_{sn})
* **Neck height**: (h_{sn})
* **Wedge seat angle(s)** or taper: (\beta_w) (or specify top/bottom widths)
* **Wedge pocket depth**: (h_w) (if you model it)

**Slot body**

* **Slot body top width**: (b_{sb1})
* **Slot body bottom width**: (b_{sb2}) (or constant width (b_{sb}))
* **Slot body height**: (h_{sb})
* **Sidewall taper**: (\gamma) (optional, if not using (b_{sb1}, b_{sb2}))

**Slot bottom**

* **Slot bottom radius/fillet**: (r_{sb,f})
* **Slot bottom corner radii**: (r_{c1}, r_{c2}) (optional)
* **Tooth root fillet radius**: (r_{tr})

From these, the **slot depth** is:

* (h_s = h_{so} + h_{sn} + h_{sb} +) (any bottom feature depth)

And the **tooth width at slot bottom** is set by circumference minus slot bottom width at the relevant radius.

---

## 6) Insulation and conductor window geometry (if you model “usable area”)

If your “fully specify geometry” includes the **electrical window** (often crucial for thermal/packing calculations), add:

* **Slot liner thickness** (side): (t_{ins,side})
* **Slot liner thickness** (bottom): (t_{ins,bot})
* **Slot liner thickness** (top/mouth): (t_{ins,top})
* **Wedge thickness**: (t_{w})
* **Phase insulation / separators** thickness: (t_{sep}) (if present)
* **Corner insulation radii** or effective offsets: (r_{ins})

These define:

* **Net copper window area** (A_{cu,\text{win}}) and its polygon/fillets.

---

## 7) Axial/3D stator stack geometry

Even if your electromagnetic model is 2D, manufacturing and losses depend on the axial definitions.

* **Active stack length**: (L_{stk})
* **Number of laminations**: (N_{lam})
* **Lamination thickness**: (t_{lam})
* **Interlam insulation / coating thickness**: (t_{coat}) (optional)
* **Stacking factor**: (k_{stk}) (not geometry per se, but used as an effective axial fill)
* **Skew angle**: (\theta_{sk}) (or skew pitch in slots)
* **Segment count (if segmented stator)**: (N_{seg}) and **segment gap** (g_{seg})
* **Step skew profile** (if discrete): number of steps (N_{sk,step}), step angles ({\Delta\theta_i})

---

## 8) Cooling and structural features that cut the iron (geometry-affecting)

If present, these must be specified to “fully” define the stator solid.

* **Ventilation ducts / axial vents**:

  * **Number of ducts**: (N_{duct})
  * **Duct axial positions**: ({z_i})
  * **Duct thickness**: (t_{duct})
  * **Duct inner/outer radii**: (R_{duct,i}, R_{duct,o})
* **Radial cooling channels** (if embedded in yoke):

  * channel count (N_{ch}), size/shape parameters (e.g., width/height), angular positions ({\theta_i})
* **Mounting keyways / notches**:

  * keyway depth/width, angular position
* **Bolt holes / tie rods**:

  * count, hole diameter, bolt circle radius, angular offset

---

## 9) End geometry (optional, but often needed for “full stator” CAD)

If “stator geometry” includes end-winding space and end structures:

* **End lamination chamfer**: (c_{end}) (or end radius)
* **End plate / retaining ring features** (if part of stator assembly):

  * thicknesses, inner/outer radii, bolt patterns
* **Slot liner overhang length**: (l_{liner,oh})
* **Wedge overhang length**: (l_{w,oh})

(Strictly speaking, **end-turn copper geometry** is winding geometry, but it’s commonly coupled to stator slot and end-space constraints.)

---

## 10) “Derived but important” geometric outputs (useful to validate your inputs)

Not inputs, but you typically compute these to sanity-check the parameter set:

* Tooth width vs radius: (b_t(r))
* Yoke minimum thickness
* Slot area (gross / net copper)
* Minimum bridge thickness at tooth tips
* Stator iron area and mass estimate
* Sector periodicity angle for FEA

---

### If you want the *minimal* parameter set

For a straightforward 2D semi-closed slot lamination without ducts/holes/segmentation, a very common minimal set is:

* (Q_s, D_{so}, D_{si})
* Slot opening: (b_{so}, h_{so})
* Neck: (b_{sn}, h_{sn})
* Body: (b_{sb1}, b_{sb2}, h_{sb})
* Fillets: (r_{so,f}, r_{sb,f}, r_{tr})
* Stack: (L_{stk}) (and optionally (\theta_{sk}))

---

If you tell me which stator slot family you’re using (e.g., open rectangular, semi-closed trapezoid, rounded-bottom, dovetail, etc.) and whether you need **manufacturing features** (holes/ducts/keyway), I can collapse this into a clean *exact* variable list for that family (with a diagram-style naming convention that matches common CAD/FEA templates).
