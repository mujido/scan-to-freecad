"""Register a reference model (the user's own CAD, exported as .npz via fc_export.export_mesh or as .stl) onto the scan.

Tries all 24 axis-aligned orientations (plus mirrored ones with --allow-mirror) from a centroid match, refines each
briefly with trimmed point-to-point ICP, then polishes the best. Trimming (--keep) lets it lock on even when the
reference differs from the scan on purpose (filled pockets, print-oriented changes).

Writes the 4x4 reference->scan transform. In FreeCAD apply it by setting the shape's Placement
(App.Placement(App.Matrix(...))) - not transformGeometry, which converts to B-splines and breaks booleans.

Example:  python register.py aligned.npy reference.npz --out ref_to_scan.json
"""
import argparse
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from scipy.spatial import cKDTree
from _common import load_cloud, load_mesh, sample_mesh, save_transform


def icp(P, tree, target, R, t, iters, keep):
    for _ in range(iters):
        Q = P @ R.T + t
        dist, j = tree.query(Q)
        m = dist <= np.quantile(dist, keep)
        A, B = Q[m], target[j[m]]
        ca, cb = A.mean(0), B.mean(0)
        U, _, Vt = np.linalg.svd((A - ca).T @ (B - cb))
        D = np.diag([1, 1, np.sign(np.linalg.det(Vt.T @ U.T))])
        dR = Vt.T @ D @ U.T
        R, t = dR @ R, dR @ (t - ca) + cb
    dist = tree.query(P @ R.T + t)[0]
    return R, t, float(np.median(dist)), float(np.quantile(dist, keep))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cloud'); ap.add_argument('reference')
    ap.add_argument('--out', required=True)
    ap.add_argument('--keep', type=float, default=0.7, help='fraction of closest pairs used per ICP step')
    ap.add_argument('--allow-mirror', action='store_true')
    a = ap.parse_args()
    target = load_cloud(a.cloud)[:, :3]
    v, f = load_mesh(a.reference)
    P, _ = sample_mesh(v, f, 60000)
    tree = cKDTree(target)
    results = []
    for perm in itertools.permutations(range(3)):
        for sg in itertools.product([1, -1], repeat=3):
            R = np.zeros((3, 3))
            for r, (c, s) in enumerate(zip(perm, sg)):
                R[r, c] = s
            if np.linalg.det(R) < 0 and not a.allow_mirror:
                continue
            t = target.mean(0) - P.mean(0) @ R.T
            results.append(icp(P, tree, target, R, t, 15, a.keep))
    results.sort(key=lambda r: r[2])
    print('best candidates (median distance):', [round(r[2], 3) for r in results[:4]])
    if len(results) > 1 and results[1][2] < results[0][2] * 1.3:
        print('WARNING: two orientations fit almost equally well (symmetric part?) - check the result visually')
    keep = min(0.9, a.keep + 0.1)
    R, t, med, q = icp(P, tree, target, results[0][0], results[0][1], 60, keep)
    ang = np.degrees(np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1)))
    T = np.eye(4); T[:3, :3] = R; T[:3, 3] = t
    save_transform(a.out, T, median=med, mirrored=bool(np.linalg.det(R) < 0))
    print(f'final median {med:.3f}  ({int(keep * 100)}% of points within {q:.3f})  rotation {ang:.1f} deg'
          f'  mirrored={np.linalg.det(R) < 0}')
    print('matrix rows:'); print(np.round(T, 5))


if __name__ == '__main__':
    main()
