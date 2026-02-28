I’ll outline the main geometric parameter sets and math representations used to define turbine blade shape—from 2D airfoil sections to 3D stacking, twist, lean/sweep, and endwall features—plus common equations and file formats used in practice.


A turbine blade is usually defined as a *family of 2D airfoil sections* placed along the span and then “stacked” with prescribed *twist, lean, sweep,* and *thickness/camber* distributions—plus platform/endwall and tip features. Below are the main formula/parameter groups people use in industry and research.

---

## 1) Coordinate systems and basic quantities

**Blade-fixed coordinates**

* (s): meridional (streamwise along hub–shroud surface / passage centerline)
* (r): radius (span direction)
* (\theta): circumferential angle

**Common blade design scalars**

* **Span**: (H = r_{tip}-r_{hub})
* **Chord** at a section: (c)
* **Pitch**: (p = \dfrac{2\pi r}{N}) (with (N) blades)
* **Solidity**: (\sigma = \dfrac{c}{p})
* **Stagger angle**: (\gamma) (airfoil chord line vs axial/meridional reference)
* **Metal angles** (blade geometric inlet/outlet angles): (\beta_{1,m}), (\beta_{2,m})
* **Wedge / trailing edge angle**: (\delta_{TE})
* **Leading edge radius** (R_{LE}), trailing edge thickness (t_{TE})

---

## 2) 2D airfoil section definition (hub/mid/tip, etc.)

Most 3D blades are built from several 2D sections. Each section is defined by:

* **Camber line** (or mean line)
* **Thickness distribution**
* **Leading/trailing edge closure**
* **Scaling & orientation** (chord, stagger, metal angles)

### 2.1 Camber line (meanline) parameters

Two common parameterizations:

**A) Meanline via inlet/outlet angles**
Define a curve whose end tangents match (\beta_{1,m}) and (\beta_{2,m}).
A generic approach is a polynomial or spline for the camber line (y_c(x)) on (x\in[0,c]), with constraints:

* (y_c(0)=0), (y_c(c)=0)
* (y_c'(0)=\tan(\beta_{1,m}-\gamma))
* (y_c'(c)=\tan(\beta_{2,m}-\gamma))

Often implemented with **cubic splines** or **Bezier curves**.

**B) Meanline as a circular arc**
Sometimes approximated as an arc with camber angle (\theta_c) and radius (R):

* Arc length (\approx c)
* Curvature (\kappa = 1/R)
  This is simpler but less flexible than splines.

### 2.2 Thickness distribution

Let thickness as a function of normalized chord (u=x/c) be (t(u)). Then:

* Upper surface: ( \mathbf{x}_u = \mathbf{x}_c + \dfrac{t(u)}{2},\mathbf{n}(u))
* Lower surface: ( \mathbf{x}_\ell = \mathbf{x}_c - \dfrac{t(u)}{2},\mathbf{n}(u))

where (\mathbf{x}_c) is the camber line point and (\mathbf{n}(u)) is the unit normal to the camber line.

Typical thickness parameter sets include:

* max thickness (t_{max})
* location of max thickness (u_{tmax})
* LE radius (R_{LE})
* TE thickness (t_{TE})
* optional “pressure-side vs suction-side” bias (asymmetric thickness)

A practical engineering representation is again **splines** through control points:
[
t(u) = \text{spline}\Big((u_i,, t_i)\Big)
]

### 2.3 Leading/trailing edge closure

To avoid cusps and control curvature:

* LE often defined as a circle/ellipse blend: curvature set by (R_{LE})
* TE defined by thickness (t_{TE}) and wedge angle (\delta_{TE}), with a smooth blend into the aft thickness curve

---

## 3) Section placement in 3D: stacking and spanwise laws

You choose a set of span stations (r_i) (or span fraction (\eta\in[0,1])) and define section parameters as functions of span.

### 3.1 Chord, thickness, and camber scaling along span

Examples:

* (c(\eta))
* (t_{max}(\eta))
* (\beta_{1,m}(\eta), \beta_{2,m}(\eta))
* (R_{LE}(\eta), t_{TE}(\eta))

These are typically:

* piecewise-linear, polynomial fits, or B-splines in (\eta)

### 3.2 Twist (spanwise rotation)

Twist is the rotation of each section about a stacking axis (often near the leading edge or centroid):
[
\gamma(\eta) = \text{twist law}
]
Applied as a rotation matrix (R_z(\gamma)) (or about the local radial axis depending on coordinate convention).

### 3.3 Sweep and lean (stacking-line offsets)

Define the stacking line (\mathbf{S}(\eta)) giving the section origin offset in meridional/circumferential directions:

* **Sweep**: chordwise/streamwise displacement of sections
* **Lean**: circumferential displacement (often used to control secondary flows)

A common representation:
[
\mathbf{S}(\eta) =
\begin{bmatrix}
\Delta s(\eta)\
\Delta \theta(\eta)\
r(\eta)
\end{bmatrix}
]
with (\Delta s(\eta)) and (\Delta \theta(\eta)) given by splines/control points.

---

## 4) Defining the blade surface: ruled vs spline surfaces

Once you have section curves (\mathbf{C}_i(u)) at each span station, the blade surface is typically a **loft**:

**Spline loft (most common CAD/CAE)**
[
\mathbf{X}(u,\eta) = \text{surface_spline}\left(\mathbf{C}_i(u)\right)
]

**Simpler “ruled” surface** (less common for final aero surfaces)
[
\mathbf{X}(u,\eta) = (1-\eta)\mathbf{C}*{hub}(u)+\eta,\mathbf{C}*{tip}(u)
]
Not great for real blades because it can distort curvature.

---

## 5) Endwall/platform, fillets, and tip features (often separate parameter sets)

A turbine blade is not just the airfoil:

* **Hub/platform**: platform contour curves, thickness, fillet radii
* **Shroud** (for shrouded blades): shroud geometry, knife seals, contact faces
* **Tip** (unshrouded): tip thickness, squealer tip cavity depth, rim width, tip corner radii
* **Endwall contouring**: endwall surface defined by its own spline height function (h_{EW}(s,\theta))

These are usually handled as:

* additional surfaces blended to the airfoil with G1/G2 continuity constraints
* explicit parameters: fillet radius distributions (R_f(\eta)), squealer depth (d_{sq}), etc.

---

## 6) The “minimal” parameter list people actually optimize

If you want a compact set that still spans useful shapes, a typical optimization-friendly set is:

**Per span station (hub/mid/tip or 5–9 stations):**

* (c), (\gamma) (stagger), (\beta_{1,m}), (\beta_{2,m})
* (t_{max}), (u_{tmax}), (R_{LE}), (t_{TE}), (\delta_{TE})
* 2–6 thickness control points on each side (or a single thickness spline + asymmetry factor)

**Spanwise distributions:**

* twist law (\gamma(\eta)) (or (\beta_{2,m}(\eta)))
* sweep (\Delta s(\eta))
* lean (\Delta \theta(\eta))
* optional: bow/dihedral, stacking axis location (x_{stack}(\eta))

---

## 7) Common math representations in practice

You’ll see these a lot in actual blade geometry pipelines:

* **B-splines / NURBS** for curves and surfaces (CAD-standard)

  * Airfoil edges as NURBS; blade surface as NURBS loft
* **Bezier curves** for camber and thickness distributions (easy constraints, few parameters)
* **CST (Class-Shape Transformation)** for airfoil-like shapes

  * Parameterizes surfaces with a class function (C(u)) and shape function (S(u))
* **PARSEC-like parameters** (more common in compressor/airfoil literature than turbine, but still used)

  * Uses parameters like LE radius, max thickness, curvature constraints, etc.

---

## 8) If you tell me your context, I can tailor it

If your goal is **CAD definition**, **CFD meshing**, or **conceptual design/optimization**, the “best” parameterization differs a lot. But the structure above (2D sections + stacking laws + end features) is the standard mental model.

If you want, tell me:

* rotor vs stator, and whether it’s **axial** or **radial** turbine
* how many span stations you plan to use (e.g., 3 vs 7)
* whether you prefer **NURBS**, **Bezier**, or **CST**
  and I’ll propose a clean, explicit parameter vector (\mathbf{p}) with equations for generating the full 3D surface.
