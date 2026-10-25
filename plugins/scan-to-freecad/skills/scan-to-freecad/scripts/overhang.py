"""Overhang check for a print orientation.

Give the print "up" direction in the model frame, either directly (--up "0.81,0,0.58") or as the outward normal of
the face that sits on the bed (--bed-normal "-0.81,0,-0.58"). Faces whose normal points down more steeply than
--limit (default 45 deg from horizontal) and that are not on the bed are reported as needing support.

--regions regions.json  per-region overhang area, e.g. {"outer rails": "abs(cy)>10.9"}  (cx cy cz = face centre;
                        nx ny nz = face normal)

Example:  python overhang.py model.npz --bed-normal "-0.813,0,-0.582" --regions regions.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from _common import load_mesh


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('model')
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--up'); g.add_argument('--bed-normal')
    ap.add_argument('--limit', type=float, default=45.0, help='self-supporting limit, degrees from horizontal')
    ap.add_argument('--regions')
    a = ap.parse_args()
    v, f = load_mesh(a.model)
    up = np.array([float(x) for x in (a.up or a.bed_normal).split(',')])
    up = up / np.linalg.norm(up) * (1 if a.up else -1)
    A, B, C = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    n = np.cross(B - A, C - A); ar = np.linalg.norm(n, axis=1) / 2; n /= np.maximum(2 * ar, 1e-12)[:, None]
    h = np.stack([A, B, C], 1) @ up
    on_bed = h.max(1) < (v @ up).min() + 0.05
    down = -(n @ up)                                  # 1 = horizontal ceiling, 0 = vertical wall
    face_angle = np.degrees(np.arccos(np.clip(down, -1, 1)))   # angle of the face from horizontal, for down-facing faces
    bad = (down > np.cos(np.radians(a.limit))) & ~on_bed & (h.min(1) > (v @ up).min() + 0.3)
    ctr = (A + B + C) / 3
    print(f'height in print orientation: {(v @ up).max() - (v @ up).min():.1f}   bed contact area: {ar[on_bed].sum():.1f} mm2')
    print(f'overhang steeper than {a.limit:g} deg: {ar[bad].sum():.1f} mm2'
          + (f'  (worst face {face_angle[bad].min():.0f} deg from horizontal)' if bad.any() else ''))
    if a.regions:
        env = {'cx': ctr[:, 0], 'cy': ctr[:, 1], 'cz': ctr[:, 2], 'nx': n[:, 0], 'ny': n[:, 1], 'nz': n[:, 2], 'abs': np.abs, 'np': np}
        for name, expr in json.load(open(a.regions)).items():
            m = np.asarray(eval(expr, {'__builtins__': {}}, env), bool)
            sel = m & ~on_bed & (down > 0)
            worst = face_angle[sel].min() if sel.any() else float('nan')
            print(f'  {name:28s} overhang {ar[m & bad].sum():7.1f} mm2   worst down-facing face {worst:.0f} deg from horizontal')


if __name__ == '__main__':
    main()
