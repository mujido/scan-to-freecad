# FreeCAD traps that cost time in scan-to-CAD work

Read before writing a build script. Each item is something that actually broke or silently produced wrong geometry.

## Coordinate frames and attachment
- Origin plane orientation (FreeCAD 1.x): **XY** u=X v=Y normal +Z; **XZ** u=X v=Z normal **-Y**; **YZ** u=Y v=Z normal +X. So a sketch on XZ offset by `+10` along its normal sits at y = -10. Print the origin features' Placements once if unsure.
- `AttachmentOffset` is in sketch-local coordinates (u, v, normal). Its rotation is about sketch-local axes: (1,0,0) tilts the sketch plane about u (e.g. to slope a channel), (0,0,1) spins the profile in-plane (e.g. aim a teardrop).
- Pocket/Pad direction defaults to the sketch normal (pocket goes opposite). Rather than reasoning about `Reversed`, set `UseCustomVector=True` and an explicit `Direction`. Check the volume change after recompute to confirm it cut what you meant.
- An expression can drive a single vector component, e.g. `pocket.setExpression('.Direction.y', '-Params.Side')` - handy for "which side" switches.
- PartDesign primitives with no attachment use their `Placement` directly; drive `.Placement.Base.x/y/z` and `.Placement.Rotation.Angle` by expression (set the rotation axis once in Python).

## Sketches
- Add constraints with their **real current values** (evaluate the expression first), then attach the expression. Adding `DistanceX = 1.0` and fixing it later makes the solver move geometry, which flips arcs and crosses lines; you get solve status -3 or a self-intersecting profile.
- Pin polygon vertices with DistanceX/DistanceY from the root point (-1, 1). Negative values are fine for these.
- `ArcOfCircle(circle, a1, a2)` runs counter-clockwise from a1 to a2; position 1 = start, 2 = end, 3 = centre.
- After building, check every sketch: `sk.solve() == 0` and `sk.FullyConstrained` is True.

## Features and the tree
- `PartDesign::Mirrored` does not always become the body's Tip; set `body.Tip = mirrored` or later features build on the pre-mirror shape (the mirror silently "disappears" from the result).
- Mirroring a **rotated** additive/subtractive primitive (together with other originals) produced an invalid shape several features later. Build the mirrored copy as a second explicit primitive instead.
- Feature tapers apply to **every** wall of the profile. If only some edges should be sloped, split the profile into separate pockets.
- Fillets/chamfers picked by edge name break when earlier features change (topological naming). Prefer profile geometry; if needed, put them last.
- After a recompute, read the state of every feature. A feature can show 'Up-to-date' with an invalid shape - check `o.Shape.isValid()` and the solid count, not just the state.
- `body.Shape.BoundBox` can be loose (includes tool geometry slop); use `optimalBoundingBox()` for real extents.

## Booleans, imports, comparisons
- To move an imported reference shape, set `shape.Placement` (re-orthonormalise the rotation first). `transformGeometry` converts faces to B-splines and later `common`/`cut` returned empty or nonsense results.
- `shape.isInside(...)` on B-spline geometry is slow (tens of ms per call). Thousands of probes inside the GUI froze FreeCAD for 15+ minutes and queued every later bridge call. Export a mesh and do bulk inside/outside or distance work outside FreeCAD.
- If FreeCAD stops responding during a script, it may simply be busy (check CPU). The bridge cannot interrupt it; ask the user before force-closing, and make sure the build script can regenerate the document so nothing is lost.

## Documents and files
- `doc.saveAs` leaves timestamped `.FCBak` backups next to the file on each save; clean up the ones your rebuilds created.
- Rebuild from the script instead of editing the live document by hand: close the old document of the same name first, then regenerate. The script is the source of truth.
- Use `doc.saveCopy(path)` for side files (e.g. a comparison document) so the main document keeps its name/path.

- Saving from headless `freecadcmd` writes no GuiDocument.xml, so all view state is lost and the model can open invisible. Setting `obj.Visibility` there doesn't help. After a headless rebuild, open the file in the GUI (bridge) and set `Gui.getDocument(...).getObject(name).Visibility` on the changed body and its tip, then save. If the GUI isn't available, tell the user the file needs one GUI save.

## Point clouds
- ASCII PLY headers vary (obj_info, comments); find `end_header` rather than assuming a line count. A wrong skip count silently parses the header line as a point (all-zero coordinates that wreck bounding boxes).
- CloudCompare-exported clouds are often centred on their bounding box, which hides the original frame; centroid != bbox centre.
- Scans of real parts often contain the mating part, fixture or a different part entirely. Render before measuring.
