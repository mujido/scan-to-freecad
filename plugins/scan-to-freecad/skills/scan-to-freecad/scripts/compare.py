"""Scan vs model deviation.

Model: .npz from fc_export.export_mesh (or an .stl), in the same frame as the scan (use --transform for the model if not).
Prints scan->model and model->scan distance stats, optional per-region stats, and writes signed deviation maps
(red = scan outside the model -> add material; blue = model outside the scan -> remove material).

--regions regions.json   {"bore": "r_xy<9.2 & abs(nz)<0.5", "outer": "..."}  (same expression language as fit.py)
--save-dev dev.npy       per-scan-point signed deviation, reusable for later region queries
--no-image               stats only (cheap)

Example:  python compare.py aligned.npy model.npz --out dev.png --regions regions.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from scipy.spatial import cKDTree
from _common import apply_transform, load_cloud, load_mesh, load_transform, mask, out_path, sample_mesh


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cloud'); ap.add_argument('model')
    ap.add_argument('--transform', help='4x4 JSON applied to the model first')
    ap.add_argument('--out', default=None); ap.add_argument('--no-image', action='store_true')
    ap.add_argument('--regions'); ap.add_argument('--save-dev')
    ap.add_argument('--samples', type=int, default=1_500_000)
    ap.add_argument('--clip', type=float, default=1.5, help='colour range +-mm')
    ap.add_argument('--px', type=float, default=0.35); ap.add_argument('--dpi', type=int, default=50)
    a = ap.parse_args()
    d = load_cloud(a.cloud); p = d[:, :3]
    v, f = load_mesh(a.model)
    T = load_transform(a.transform)
    if T is not None:
        v = apply_transform(v, T)
    q, qn = sample_mesh(v, f, a.samples)
    dist, j = cKDTree(q).query(p)
    sd = np.einsum('ij,ij->i', p - q[j], qn[j])
    pct = lambda x, k: np.percentile(x, k)
    print(f'scan->model  median {np.median(dist):.3f}  p90 {pct(dist, 90):.3f}  p99 {pct(dist, 99):.3f}'
          f'  >0.5mm {np.mean(dist > 0.5) * 100:.1f}%  >1mm {np.mean(dist > 1) * 100:.1f}%')
    d2 = cKDTree(p).query(q[::5])[0]
    print(f'model->scan  median {np.median(d2):.3f}  p90 {pct(d2, 90):.3f}  >1mm {np.mean(d2 > 1) * 100:.1f}%'
          '   (model surface the scan does not see: hidden faces or extra material)')
    if a.regions:
        for name, expr in json.load(open(a.regions)).items():
            m = mask(d, expr)
            if m.sum():
                x = dist[m]
                print(f'  {name:32s} n={m.sum():6d}  median {np.median(x):.3f}  p90 {pct(x, 90):.3f}  mean signed {sd[m].mean():+.3f}')
    if a.save_dev:
        np.save(out_path(a.save_dev), sd.astype(np.float32))
    if a.no_image or not a.out:
        return
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    views = [('+z', 2, 1, 0, 1), ('-z', 2, -1, 0, 1), ('+y', 1, 1, 0, 2), ('-y', 1, -1, 0, 2), ('+x', 0, 1, 1, 2), ('-x', 0, -1, 1, 2)]
    fig, axs = plt.subplots(3, 2, figsize=(16, 15))
    for ax, (t, k, s, i, jj) in zip(axs.ravel(), views):
        A, B = p[:, i], p[:, jj]
        ia = np.round((A - A.min()) / a.px).astype(int); ib = np.round((B - B.min()) / a.px).astype(int)
        o = np.argsort(s * p[:, k])
        img = np.full((ib.max() + 1, ia.max() + 1), np.nan); img[ib[o], ia[o]] = np.clip(sd[o], -a.clip, a.clip)
        im = ax.imshow(img, origin='lower', extent=(A.min(), A.max(), B.min(), B.max()), cmap='RdBu_r', vmin=-a.clip, vmax=a.clip,
                       interpolation='nearest')
        ax.set_title(f'from {t}  (red: scan outside model, blue: model outside scan)', fontsize=9)
        ax.set_xlabel('xyz'[i]); ax.set_ylabel('xyz'[jj]); ax.grid(True, alpha=0.3); ax.tick_params(labelsize=7)
    plt.colorbar(im, ax=axs, shrink=0.5)
    plt.savefig(out_path(a.out), dpi=a.dpi)
    print('wrote', a.out)


if __name__ == '__main__':
    main()
