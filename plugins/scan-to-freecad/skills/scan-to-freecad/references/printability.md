# Making a print-ready variant

The as-scanned body copies the part. The print-ready body keeps everything the part needs to *function* and changes what only the original manufacturing process (usually injection moulding with metal inserts) needed. Build it as a second body in the same document with the same `Params` sheet so the user can choose either.

## First: know which surfaces are functional
Ask, or get it from the user's own model, before touching any surface:
- **Bearing / guide / sliding faces** (rails, keys, faces that ride on a mating part) keep their position and stay square. Don't taper, chamfer or blend them even if they overhang a little; a slightly steep overhang on a guide face is better than a guide that no longer contacts.
- **Mating fits** (bores, shafts, envelopes that slide into a tube) keep their measured size plus a print allowance (`HoleComp` ~0.1-0.3 mm on diameters for FDM holes; outer envelopes usually need none if the scan shows running clearance).
- **Hardware**: get the exact screw/nut/insert the user will use. Size holes and pockets from the hardware, not from the scan of the old part.

## Orientation
- Choose (or confirm) the print orientation first; every overhang judgement depends on it. Users often have a strong preference (e.g. standing the part on an angled face cut across one end so long features print without support).
- A flat print base can be an added cut (a plane across a tip) when the part has no good flat face. Make its angle and position parameters.
- Check overhangs in that orientation with `overhang.py`. Rule of thumb: faces up to ~45 deg from vertical self-support; bridges up to ~10 mm are fine.

## Patterns that worked
- **Fill pockets that only existed to save moulding material** (uniform wall thickness for injection moulding). Solid prints stronger and removes ceilings/bridges.
- **Merge metal inserts into the body** when the insert can't be replaced, then replace its function: e.g. a threaded ring becomes a captive square/hex nut pocket loaded from an internal bore, or a hole for a heat-set insert. Size from the hardware (M4 square nut 7 x 7 x 2 -> pocket ~7.4 x 7.4 with depth ~2.4 + clearance).
- **Teardrop holes** for horizontal holes: point the tip straight up *in the print orientation* (which may not be the model's +Z). Tie the teardrop angle to the print-base angle parameter so it follows if the orientation changes.
- **Features whose corner points at the bed** (a rib or fin whose leading corner is the lowest point when printed) start printing in mid-air. Don't fix this by sloping the faces that touch a mating part; instead make the feature **grow out of the surface along a shallow wedge** (its outer face a plane a few degrees off the base surface, starting at zero height), so each layer extends only slightly beyond the one below. Keep the functional face square.
- **Steps that face up** in the print orientation need no change. Only treat faces that point down.
- When the print variant shortens or moves one feature, check every feature that was sized from it (a channel whose length was tied to a pocket that got shorter will now cut into a wall).

## Checks before handing over
- `overhang.py` in the print orientation, overall and per functional region.
- Point probes on each functional face: solid just inside, open just outside, on both sides of a symmetric part.
- Volume and body validity; STL closed and manifold.
- An STL already rotated into the print orientation, base on Z=0.
- Say what was not verified: no test print, hardware fit untested.
