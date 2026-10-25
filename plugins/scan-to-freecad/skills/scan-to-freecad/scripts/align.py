"""Align a cloud and report its envelope and mirror symmetry.

Modes
  pca       principal axes -> X longest, Y middle, Z shortest; centred on the bounding-box centre
  cylinder  fit the dominant cylinder (trimmed least squares on the outer skin); its axis -> --axis-to (default x)
  none      keep the frame, only report (use when the scan is already aligned)

Symmetry check: mirrors the cloud across each coordinate plane through the bbox centre and reports the median
distance to the nearest original point. Near scanner noise (~0.1-0.2 mm) = that plane is a mirror plane.

Example:  python align.py cloud.npy aligned.npy --mode pca --transform T.json
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial import cKDTree
from _common import load_cloud, out_path, save_transform


def fit_cylinder(p, axis0):
    """Trimmed fit of the outer cylindrical skin. Returns (axis unit vector, point on axis, radius, residual std)."""
    axis0 = axis0 / np.linalg.norm(axis0)
    u = np.cross(axis0, [1, 0, 0] if abs(axis0[0]) < 0.9 else [0, 1, 0]); u /= np.linalg.norm(u)
    w = np.cross(axis0, u)
    c0 = p.mean(0)

    def unpack(q):
        a = axis0 + q[0] * u + q[1] * w
        a /= np.linalg.norm(a)
        return a, c0 + q[2] * u + q[3] * w

    def res(q, P):
        a, c = unpack(q)
        v = P - c
        return np.linalg.norm(v - np.outer(v @ a, a), axis=1) - q[4]

    v = p - c0
    r0 = np.median(np.linalg.norm(v - np.outer(v @ axis0, axis0), axis=1))
    q = np.array([0, 0, 0, 0, r0])
    P = p
    for _ in range(5):
        q = least_squares(res, q, args=(P,), loss='soft_l1', f_scale=0.2).x
        r = res(q, p)
        P = p[np.abs(r) < max(0.6, 3 * np.std(r[np.abs(r) < 1]))]   # keep the outer skin, drop inner walls
    a, c = unpack(q)
    return a, c, q[4], res(q, P).std()


def frame_from_axis(a, to='x'):
    a = a / np.linalg.norm(a)
    if a[np.argmax(np.abs(a))] < 0:
        a = -a
    ref = np.array([0, 0, 1.0]) if abs(a[2]) < 0.9 else np.array([1.0, 0, 0])
    e2 = ref - (ref @ a) * a; e2 /= np.linalg.norm(e2)
    e1 = np.cross(e2, a)
    rows = {'x': [a, e1, e2], 'y': [e2, a, e1], 'z': [e1, e2, a]}[to]
    R = np.vstack(rows)
    if np.linalg.det(R) < 0:
        R[1] *= -1
    return R


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cloud')
    ap.add_argument('out')
    ap.add_argument('--mode', choices=['pca', 'cylinder', 'none'], default='pca')
    ap.add_argument('--axis-to', choices=['x', 'y', 'z'], default='x', help='cylinder mode: which axis the cylinder axis becomes')
    ap.add_argument('--transform', help='write the 4x4 original->aligned transform to this JSON')
    a = ap.parse_args()
    d = load_cloud(a.cloud)
    p, n = d[:, :3], d[:, 3:6]
    R, c = np.eye(3), np.zeros(3)
    if a.mode == 'pca':
        c = p.mean(0)
        w, v = np.linalg.eigh(np.cov((p - c).T))
        R = v[:, ::-1].T
        if np.linalg.det(R) < 0:
            R[2] *= -1
    elif a.mode == 'cylinder':
        w, v = np.linalg.eigh(np.cov((p - p.mean(0)).T))
        axis, c, r, s = fit_cylinder(p[::max(1, len(p) // 150000)], v[:, 2])
        print(f'cylinder: axis {np.round(axis, 4)}  radius {r:.3f}  diameter {2 * r:.3f}  skin residual std {s:.3f}')
        R = frame_from_axis(axis, a.axis_to)
    q = (p - c) @ R.T
    shift = -(q.min(0) + q.max(0)) / 2 if a.mode != 'none' else np.zeros(3)
    q += shift
    T = np.eye(4); T[:3, :3] = R; T[:3, 3] = shift - R @ c
    np.save(out_path(a.out), np.hstack([q, n @ R.T]).astype(np.float32))
    if a.transform:
        save_transform(a.transform, T, mode=a.mode)
    lo, hi = q.min(0), q.max(0)
    print(f'aligned bbox min {np.round(lo, 2)} max {np.round(hi, 2)} size {np.round(hi - lo, 2)}')
    sub = q[np.random.default_rng(0).choice(len(q), min(20000, len(q)), replace=False)]
    tree = cKDTree(q)
    ctr = (lo + hi) / 2
    for k, name in enumerate('xyz'):
        m = sub.copy(); m[:, k] = 2 * ctr[k] - m[:, k]
        dist = tree.query(m)[0]
        # best offset of the mirror plane (handles a slightly off-centre plane)
        best = min(((np.median(tree.query(m + np.eye(3)[k] * s)[0]), s) for s in np.linspace(-1, 1, 21)), key=lambda t: t[0])
        print(f'mirror across plane {name}={ctr[k]:+.2f}: median gap {np.median(dist):.3f}'
              f'  (best {best[0]:.3f} with plane shifted {best[1] / 2:+.2f})')


if __name__ == '__main__':
    main()
