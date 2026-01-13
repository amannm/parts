I’ll outline the full set of parameters engineers use to define a screw thread across the major standards (ISO metric and Unified), including what’s mandatory vs optional for a complete drawing/callout.


Here’s a comprehensive checklist of **input variables/parameters** used to **fully specify a screw thread** (i.e., enough to manufacture/inspect and avoid ambiguity). I’ll list them in a standards-agnostic way, then note the common ISO Metric and Unified (UNC/UNF) equivalents.

## Core thread definition (always needed)

1. **Thread system / standard**

   * e.g., ISO Metric (M), Unified (UN/UNC/UNF/UNEF), Whitworth, Acme/Trapezoidal, Pipe (NPT/BSP), etc.

2. **Thread form / profile**

   * Included angle (e.g., 60°, 55°, 29° for Acme)
   * Crest/root shape rules (flat, rounded, truncation radii)

3. **Nominal size**

   * For most fastener threads: nominal **major diameter** (or “size” designation)
   * Examples: `M10`, `1/4`, `G1/2`, etc.

4. **Pitch (or TPI)**

   * Pitch (mm per thread) for metric
   * Threads per inch (TPI) for inch-series

5. **Hand**

   * Right-hand (default) or left-hand (LH)

6. **Thread series (if applicable)**

   * Unified: UNC / UNF / UNEF / UNS, etc.
   * Metric often implies “coarse/fine” via pitch, but series can still be referenced.

7. **Thread class / tolerance class**

   * Defines allowances and tolerances
   * Unified: `1A/2A/3A` (external), `1B/2B/3B` (internal)
   * ISO metric: e.g., `6g` (external), `6H` (internal), sometimes combos like `6g6g`

8. **Internal vs external**

   * Male (external) vs female (internal) matters for class, gaging, and truncations.

## Engagement / length definition (to make it manufacturable)

9. **Thread length / engagement length**

   * Length of full thread or minimum thread engagement
   * For holes: thread depth (full + partial), and whether it’s thru or blind

10. **Thread runout / incomplete thread allowance**

* How much imperfect thread is acceptable at ends (often controlled indirectly but can be specified)

## Start, lead, and multi-start details (when not default)

11. **Number of starts**

* Single-start (default) or multi-start

12. **Lead**

* Lead = pitch × number of starts (critical for multi-start)

## Diameter and fit-control details (needed when doing more than a simple callout)

These are often *derived* from size + pitch + class, but can be explicit inputs if you’re doing custom/nonstandard or inspection-critical work:

13. **Major diameter limits** (max/min)
14. **Pitch diameter limits** (max/min) — the most important functional diameter
15. **Minor diameter limits** (max/min)
16. **Crest/root truncation or radius limits** (especially for special forms)

## Special thread types (add as applicable)

17. **Taper**

* Taper per length or angle (e.g., pipe threads)
* Plus which diameter is referenced at which gauge plane

18. **Sealing method / gage plane definition (pipe threads)**

* NPT/BSP variants may need gage plane position, L1/L2/L3 gaging, etc.

19. **Thread form variants / specials**

* Buttress, stub Acme, trapezoidal, knuckle, etc. (each has its own defining geometry set)

## Manufacturing/finish requirements (commonly required for “fully specify” on drawings)

20. **Material condition / plating or coating**

* Because coatings change effective size and fit (can require allowance changes)

21. **Surface finish on flanks**

* Especially for power screws or sealing threads

22. **Acceptance / gaging requirement**

* GO/NO-GO gage class, 3-wire method, functional gage, etc. (often implied by the standard/class, but can be explicitly required)

## Practical “complete callout” templates

* **ISO metric fastener thread:**
  `M<nominal major> × <pitch> - <tolerance class> - <hand if LH> - <thread length/depth>`
* **Unified thread:**
  `<nominal major>-<TPI> <series> - <class A/B> - <hand if LH> - <thread length/depth>`

### Example completeness check

* External: `M10×1.5-6g RH, thread length 20 mm`
* Internal: `1/4-20 UNC-2B, thru` (plus depth if blind)

If you tell me **which thread family** you mean (fastener threads like ISO/UN, power screws like Acme/Trapezoidal, or pipe threads like NPT/BSP), I can give the **minimal required inputs** for that family and a “derived vs must-specify” table.
