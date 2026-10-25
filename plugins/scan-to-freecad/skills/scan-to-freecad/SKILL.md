---
name: scan-to-freecad
description: Reverse-engineer a 3D-scanned physical part (point cloud or mesh - PLY, ASC, XYZ, PCD, STL - optionally with photos and a reference STEP) into a parametric FreeCAD PartDesign model with a spreadsheet-driven, fully constrained feature tree, plus an optional 3D-print-ready variant. Use this whenever someone wants to recreate, replicate, rebuild, model, or "reverse engineer" a real object from a scan, point cloud or photogrammetry in FreeCAD, make a replacement part from a scan, compare a CAD model against a scan, or check a scanned part's dimensions - even if they only say "I scanned this bracket, can you make a CAD model of it".
compatibility: FreeCAD 1.x (bundled Python with numpy, scipy, matplotlib). Works best with a FreeCAD MCP bridge (execute_python); without it, run the same scripts with FreeCAD's python / freecadcmd.
---

# Scan to parametric FreeCAD model

Turn a scan of a real part into a clean, parametric FreeCAD model that matches the scan within scanner noise, keeps the part's design intent, and (if wanted) prints well.

The work is mostly measurement and judgement, not modeling. Most mistakes in this kind of job come from three places: modeling the wrong thing (wrong file, wrong interpretation of a feature), guessing at design intent the user already knows, and burning context on big images. The workflow below is built to avoid those.

## Tools in this skill

All analysis scripts are plain Python + numpy/scipy/matplotlib and run with **FreeCAD's bundled interpreter**, which already has those packages (system Python often doesn't):

- Windows: `C:\Program Files\FreeCAD <ver>\bin\python.exe`
- macOS: `/Applications/FreeCAD.app/Contents/Resources/bin/python`
- Linux/AppImage: the `python` next to `freecadcmd`, or `freecadcmd -c`

Run them as separate processes (`python -I scripts/<name>.py ...`), **not** inside the FreeCAD GUI. Long loops inside the GUI process freeze FreeCAD and the MCP bridge (it queues every later call behind the stuck one).

| Script | What it does |
|---|---|
| `scripts/pcload.py` | Load PLY (ascii/binary), ASC/XYZ/TXT/CSV, PCD, STL into `cloud.npy` (x y z nx ny nz). Estimates normals if missing. |
| `scripts/align.py` | Principal-axis or cylinder-axis alignment, bounding box, mirror-symmetry check. Writes aligned cloud + 4x4 transform. |
| `scripts/views.py` | Small orthographic renders: `--kind depth` (colour = depth, best for reading heights) or `--kind shaded`. |
| `scripts/slices.py` | Cross-sections at chosen levels; can overlay model sections (red) and a second model (blue). |
| `scripts/fit.py` | Fit plane / cylinder / circle to a region you select with an expression like `"x>-27 & x<-9 & abs(y)<7.4 & nz>0.2"`. |
| `scripts/compare.py` | Scan vs model deviation: overall + per-region stats, signed deviation maps. |
| `scripts/register.py` | Fit a reference model (user's own STEP/STL) onto the scan: tries all 24 axis orientations + trimmed ICP. |
| `scripts/overhang.py` | Overhang area / worst angle for a chosen print orientation, overall and per region. |
| `scripts/fc_builder.py` | Import inside FreeCAD: spreadsheet params, expression-driven primitives, fully constrained sketch helpers (polygon, U-channel, rounded rect, teardrop), pockets, build report. |
| `scripts/fc_export.py` | Import inside FreeCAD: export a body to mesh `.npz` for compare/overhang, export sections JSON for `slices.py`, save small screenshots. |

Every script prints `--help`. Keep intermediate files in a scratch folder, not the user's project folder.

Usage notes:
- Region expressions read naturally: `"z>12.5 & nz>0.95"` works (each `&`/`|` term is parenthesised for you). Variables: `x y z nx ny nz r_xy r_yz r_xz`, plus `abs` and `np`.
- Lists that start with a minus sign need `=`: `--levels="-26,-14,0,14"`, `--bed-normal="-0.81,0,-0.58"`.
- `fit.py cylinder` on a selection that also catches other surfaces: narrow it with normals (e.g. `nz<-0.3` for the underside of a horizontal cylinder) and pass `--r0` with a rough radius.
- The FreeCAD helpers also run headless: put the build in a `.py` file that starts with `import FreeCAD as App` and run `freecadcmd build.py`. That's useful when the bridge is unavailable, and for long jobs that would otherwise block the GUI.
- Load the FreeCAD helpers in the bridge with `sys.path.insert(0, r'<skill>/scripts'); import fc_builder, fc_export` (`importlib.reload` them after edits).

Read `references/freecad-pitfalls.md` before writing the build script (it lists the API traps that cost real time). Read `references/printability.md` before making a print-ready variant.

## Workflow

### 1. Intake - confirm what you are looking at before measuring anything

1. Inventory the files. Load every scan with `pcload.py` and render it (`views.py --kind shaded`) **before** asking detailed questions. Check it is the part the user means: file names lie (a "handle" scan can be the tube the part fits into), and scans can contain fixtures, turntables or mating parts.
2. If there are photos, look at them once and write a short text inventory of the features they show (holes, inserts, slots, mating parts, how it mounts). Use that text afterwards rather than re-opening the photos.
3. Ask only what you cannot infer, in one batch. The answers that change the model most:
   - **Function**: what mates with it, which surfaces bear/slide/guide/contact (these must stay accurate and usually square), what hardware goes in (screw/nut sizes, inserts).
   - **Goal**: faithful copy, or replacement to 3D print (process, materials, print orientation if they already have one), or both.
   - **Merges and deviations**: metal inserts to merge into the body, features to drop or add, deliberate asymmetries ("set screw on one side only").
   - **Units and trust**: units (assume mm if the size is plausible), known-good caliper dimensions, areas where the scan is poor.
   - **Deliverable**: feature tree in FreeCAD (default), STEP, STL.
4. If the user already reverse-engineered the part themselves and offers their model, ask for it: it is the best source of design intent (see step 7).

### 2. Load, align, check symmetry

- `pcload.py` -> `align.py`. Use `--mode cylinder` for parts whose envelope is mainly a cylinder (bushings, tube inserts), `--mode pca` otherwise, `--mode none` if the user says it's already aligned (still run it: it reports the mirror-symmetry residual).
- A mirror-symmetry residual near scanner noise (~0.1-0.2 mm) confirms the mirror plane. Larger means misalignment or genuine asymmetry - find out which before modeling.
- "The alignment looks slightly off" often isn't the scan: features can genuinely lean (e.g. a bore and channel 4-5 deg off the top face, both perpendicular to each other). If several unrelated features lean by the same angle, it is probably real geometry - keep it as a parameter and tell the user.

### 3. Understand the shape

Build a written **feature inventory** before modeling: each feature, its type (plane, cylinder, pocket, slot...), which fit or slice will measure it, and its likely design intent. Use:

- `views.py --kind depth` from 6 directions: colour shows height/depth, which reads pockets, steps and rails far better than shading.
- `slices.py` along each axis at 5-15 levels. Thin slab thickness (0.2-0.3 mm) for dense clouds, thicker for sparse ones.
- A map of where side faces stand proud (rails, ribs) - render one side with `views.py --kind depth` and a narrow colour range.

Keep images small (`--px 0.3`-`0.4` mm/pixel, default dpi). An image costs context every turn after it is viewed; numbers don't.

### 4. Measure

Use `fit.py` with region expressions; record every value with its residual and the region used. Fitting tips:

- Fit the dominant envelope first (outer cylinder / top plane), then everything relative to it.
- Use normals to separate surfaces that share a region (`nz>0.9` for upward floors, inward-pointing radial normals for bores).
- Plane fits on opposing walls give draft angles: equal and opposite lean = draft (model straight unless told otherwise); same-direction lean = real tilt.
- Snap to round values only when the user wants a "clean" design-intent model or when the fit is within noise of a standard size (M3/M4 clearances, 0.5 mm steps). Otherwise keep the measured value.
- Circle fits on a slice are the fastest way to get hole diameters/centres; `fit.py circle --axis y` etc.

### 5. Model in FreeCAD

Write the model as **one build script** (kept in the user's project folder so it can be re-run) that creates:

- A small `Params` spreadsheet of **knobs** - the 10-15 values someone will actually tune - grouped by why they'd change them (Fit, Hardware, Printing, Strength), each with a one-line note on what it does and a sensible range. Ask in intake what the user expects to adjust, and whenever you're unsure whether a dimension deserves to be a knob, propose a short candidate list (name, current value, why someone might change it) and let the user pick, rather than guessing either way. Typical knobs: hole/print allowance, mating diameters, hardware sizes, side/flip switches, print angle, wall/web thicknesses.
- Everything else (measured shape: tilts, radii, offsets, pocket outlines) as plain dimensions inside the features, still fully constrained and editable in the sketch, but not presented as a knob. Keep these as named constants with comments in the build script so the measured values stay traceable. Seventy parameters with no hint of which matter is noise, not flexibility.
- A PartDesign Body whose features are named after what they are (`OuterCylinder`, `TopChannel`, `SetScrewHole` - not `Pocket003`).
- Features driven by expressions to the spreadsheet. Prefer additive/subtractive **primitives with expression placements** for boxes/cylinders, and **fully constrained sketches** for profiles (use `fc_builder.py` helpers - they pin every vertex by expression and seed constraints with real values so the solver doesn't flip arcs).
- A printed build report: every feature's status and volume, every sketch's solver status and fully-constrained flag, final bbox and validity. Read it after every run.

Order features like the part is made: envelope -> big cuts -> pockets -> holes -> small details. Put fragile edge-based features (fillets, chamfers on picked edges) last, and avoid them when a sketch profile can carry the same shape.

Test parametric robustness once the model is complete: change 4-5 key parameters (including any side/flip switches), recompute, confirm the body stays valid, then restore.

### 6. Verify against the scan

- Export the body (`fc_export.py export_mesh`) and run `compare.py`. Targets: median deviation close to scanner noise, most points within ~0.5 mm. Read the signed deviation maps: red = scan sticks out (add material), blue = model has extra.
- Overlay sections (`fc_export.py export_sections` + `slices.py --model`). This is the fastest way to see *why* a region deviates.
- Iterate on the biggest coloured regions first. Expect to find at least one mis-read feature; that is what this step is for.
- Report per-region stats for the functional surfaces (bores, mating faces, envelope).

### 7. Reference model from the user (if any)

If the user has their own CAD of the part, it is the best evidence of design intent:

1. `register.py` it onto the scan (it handles different axis conventions). Apply the transform in FreeCAD by setting the shape's **Placement**, not `transformGeometry` (the latter converts to B-splines and breaks booleans).
2. Compare with booleans (common / cut both ways) and per-region volumes, plus `compare.py` against the scan.
3. When their design differs from the scan on purpose, **read their faces** (type, normal, bounding box, cylinder centres/radii) before reproducing it - don't infer intent from a picture. Their choices usually encode function (bearing faces kept square, print-friendly transitions, hardware pockets).

### 8. Print-ready variant (if wanted)

Add it as a **second body in the same document**, built by the same script with a `printable` flag, sharing the `Params` sheet (print-only parameters in their own section, features suffixed e.g. `_P`). The as-scanned body stays untouched, so both options exist.

Before changing any surface for printability, know which surfaces are functional (step 1). Follow `references/printability.md`, then check the result with `overhang.py` in the actual print orientation, and spot-check specific faces by probing points (solid just inside, open just outside).

### 9. Export and hand over

- STEP and STL for each body, plus an STL already rotated into the print orientation if there is one. Check meshes are closed solids with no non-manifold edges.
- One or two small screenshots of the result.
- Tell the user: what the model contains (feature tree summary), how close it is (overall + functional-region numbers), every judgement call you made (leans kept, values snapped, features simplified or skipped), and what is not verified (nothing printed, hardware fit unknown).

## Working habits that keep the job cheap and correct

- Numbers before pictures: deviation stats, point probes ("is (x,y,z) inside the solid?") and fit residuals answer most questions without an image.
- Look at a picture when the question is genuinely visual (what is this feature? where does the deviation cluster?), keep it small, and don't re-render the same view repeatedly.
- After every rebuild or edit, leave the body you just changed visible with its tip (last) feature shown, and hide the other bodies and intermediate features - the user opens the file expecting to see the latest change.
- When the user corrects you about a feature, re-read the evidence (scan, their model's faces) before changing anything; a second wrong guess costs more than a quick measurement.
- Work in phases (understand -> as-scanned model -> print variant). Between phases the build script, `Params` sheet and a short notes file carry the state, so a fresh session can continue without the old images.
