"""Fit primitives to a selected region of the cloud. Prints results and optionally appends them to a JSON log.

Select points with --where using x y z nx ny nz (and r_xy r_yz r_xz, abs, np), e.g.
  "x>-27 & x<-9 & abs(y)<7.4 & z>3.5 & nz>0.2"     (an upward-facing channel floor)
  "r_xy<8.5 & r_xy>5 & abs(nz)<0.4 & z>2 & z<9.5"  (a vertical bore near the Z axis)
Using normals to pick one side of a wall is the most reliable way to separate surfaces that are close together.

  plane      trimmed least-squares plane; reports normal, tilt vs the axes, offset and residual
  cylinder   free-axis cylinder; --axis x|y|z gives the starting direction (or 'normals' to estimate it)
  circle     circle in a slice: --axis (slice normal) --level --thick

Examples:
  python fit.py aligned.npy cylinder --axis z --where "r_xy<8.5 & r_xy>5 & abs(nz)<0.4 & z>2 & z<9.5" --name bore
  python fit.py aligned.npy circle --axis y --level 10.6 --thick 0.6 --where "x>-4 & x<3 & z>5 & z<10 & abs(ny)<0.5" --name setscrew
  python fit.py aligned.npy plane --where "z>13 & nz>0.95" --name top --log fits.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from scipy.optimize import least_squares
from _common import load_cloud, mask


def plane(p, trim=3.0):
    m = np.ones(len(p), bool)
    for _ in range(4):
        c = p[m].mean(0)
        n = np.linalg.svd(p[m] - c, full_matrices=False)[2][2]
        r = (p - c) @ n
        s = np.std(r[m])
        m = np.abs(r) < max(trim * s, 0.05)
    k = int(np.argmax(np.abs(n)))
    if n[k] < 0:
        n = -n
    out = {'normal': n.round(5).tolist(), 'point': c.round(4).tolist(), 'resid_std': float(np.std(r[m])), 'n_used': int(m.sum())}
    o = [i for i in range(3) if i != k]
    # explicit form along the dominant axis, e.g. z = a + b*x + c*y
    coef = [-n[i] / n[k] for i in o]
    out['form'] = (f"{'xyz'[k]} = {c[k] - coef[0] * c[o[0]] - coef[1] * c[o[1]]:.4f} + {coef[0]:.5f}*{'xyz'[o[0]]}"
                   f" + {coef[1]:.5f}*{'xyz'[o[1]]}")
    out['tilt_deg'] = {f"toward {'xyz'[i]}": round(float(np.degrees(np.arctan(coef[j]))), 3) for j, i in enumerate(o)}
    return out


def cylinder(p, axis0, r0=None):
    axis0 = axis0 / np.linalg.norm(axis0)
    u = np.cross(axis0, [1, 0, 0] if abs(axis0[0]) < 0.9 else [0, 1, 0]); u /= np.linalg.norm(u)
    w = np.cross(axis0, u)
    c0 = p.mean(0)

    def unpack(q):
        a = axis0 + q[0] * u + q[1] * w
        return a / np.linalg.norm(a), c0 + q[2] * u + q[3] * w

    def res(q, P):
        a, c = unpack(q); v = P - c
        return np.linalg.norm(v - np.outer(v @ a, a), axis=1) - q[4]

    v = p - c0
    q = np.array([0, 0, 0, 0, r0 or np.median(np.linalg.norm(v - np.outer(v @ axis0, axis0), axis=1))])
    P = p
    for it in range(8):
        q = least_squares(res, q, args=(P,), loss='soft_l1', f_scale=0.1).x
        r = res(q, p)
        rp = res(q, P)
        mad = 1.4826 * np.median(np.abs(rp - np.median(rp)))      # robust spread: ignores other surfaces in the selection
        P = p[np.abs(r) < max(3 * mad, 0.1)]
        if len(P) < 20:
            raise SystemExit('cylinder fit lost its points - tighten --where')
    a, c = unpack(q)
    k = int(np.argmax(np.abs(a)))
    if a[k] < 0:
        a = -a
    t = -c[k] / a[k]
    c_on = c + t * a                     # where the axis crosses the plane {axis_k = 0}
    o = [i for i in range(3) if i != k]
    return {'axis': a.round(5).tolist(),
            'lean_deg': {f"toward {'xyz'[i]} per +{'xyz'[k]}": round(float(np.degrees(np.arctan(a[i] / a[k]))), 3) for i in o},
            f"axis_at_{'xyz'[k]}=0": c_on.round(4).tolist(), 'radius': round(float(q[4]), 4), 'diameter': round(float(2 * q[4]), 4),
            'resid_std': float(np.std(res(q, P))), 'n_used': int(len(P))}


def circle(u, v):
    m = np.ones(len(u), bool)
    for _ in range(4):
        A = np.c_[2 * u[m], 2 * v[m], np.ones(m.sum())]
        cu, cv, k = np.linalg.lstsq(A, u[m] ** 2 + v[m] ** 2, rcond=None)[0]
        r = np.sqrt(k + cu ** 2 + cv ** 2)
        e = np.hypot(u - cu, v - cv) - r
        m = np.abs(e) < max(3 * np.std(e[m]), 0.05)
    return {'center': [round(float(cu), 4), round(float(cv), 4)], 'radius': round(float(r), 4), 'diameter': round(float(2 * r), 4),
            'resid_std': float(np.std(e[m])), 'n_used': int(m.sum())}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cloud')
    ap.add_argument('kind', choices=['plane', 'cylinder', 'circle'])
    ap.add_argument('--where', default='')
    ap.add_argument('--axis', default='z', help="x|y|z, or 'normals' (cylinder only)")
    ap.add_argument('--r0', type=float, help='cylinder: starting radius (helps when the selection holds other surfaces)')
    ap.add_argument('--level', type=float); ap.add_argument('--thick', type=float, default=0.3)
    ap.add_argument('--name', default='fit'); ap.add_argument('--log', help='append result to this JSON file')
    a = ap.parse_args()
    d = load_cloud(a.cloud)
    m = mask(d, a.where)
    if a.kind == 'circle':
        k = 'xyz'.index(a.axis)
        if a.level is not None:
            m &= np.abs(d[:, k] - a.level) < a.thick
        o = [i for i in range(3) if i != k]
        if m.sum() < 8:
            raise SystemExit(f'only {m.sum()} points selected')
        res = circle(d[m, o[0]], d[m, o[1]])
        res['center_axes'] = ['xyz'[o[0]], 'xyz'[o[1]]]
    else:
        if m.sum() < 20:
            raise SystemExit(f'only {m.sum()} points selected')
        p = d[m, :3]
        if a.kind == 'plane':
            res = plane(p)
        else:
            if a.axis == 'normals':
                w, v = np.linalg.eigh(np.cov(d[m, 3:6].T)); axis0 = v[:, 0]
            else:
                axis0 = np.eye(3)['xyz'.index(a.axis)]
            res = cylinder(p, axis0, a.r0)
    res = {'name': a.name, 'kind': a.kind, 'where': a.where, 'n_selected': int(m.sum()), **res}
    print(json.dumps(res, indent=1))
    if a.log:
        log = json.load(open(a.log)) if os.path.exists(a.log) else []
        log = [r for r in log if r.get('name') != a.name] + [res]
        json.dump(log, open(a.log, 'w'), indent=1)


if __name__ == '__main__':
    main()
