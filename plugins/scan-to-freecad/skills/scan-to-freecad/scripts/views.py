"""Small orthographic renders of a cloud (z-buffered).

--kind depth   colour = coordinate along the view axis (reads pockets, steps, rails, heights); default
--kind shaded  grey shading from normals (reads overall shape)
--views        any of +x -x +y -y +z -z iso1 iso2 iso3 iso4 (default: the six axis views)
--where        only render points matching an expression, e.g. "y>0" for a cut-away
--clim         fix the colour range for depth views, e.g. "10,13.5" to see what stands proud of a side face

Keep --px around 0.3-0.4 (mm per pixel) and the default dpi; large images are expensive to look at.

Example:  python views.py aligned.npy views.png --kind depth --px 0.3
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from _common import load_cloud, mask, out_path

AX = {'+x': (0, 1, 1, 2), '-x': (0, -1, 1, 2), '+y': (1, 1, 0, 2), '-y': (1, -1, 0, 2), '+z': (2, 1, 0, 1), '-z': (2, -1, 0, 1)}
ISO = {'iso1': (1, 1, 0.7), 'iso2': (1, -1, 0.7), 'iso3': (-1, 1, 0.7), 'iso4': (-1, -1, -0.7)}


def render_axis(ax, p, n, view, kind, px, clim):
    k, s, i, j = AX[view]
    A, B, D = p[:, i], p[:, j], s * p[:, k]
    ia = np.round((A - A.min()) / px).astype(int); ib = np.round((B - B.min()) / px).astype(int)
    o = np.argsort(D)
    img = np.full((ib.max() + 1, ia.max() + 1), np.nan)
    if kind == 'depth':
        img[ib[o], ia[o]] = p[o, k]
        im = ax.imshow(img, origin='lower', extent=(A.min(), A.max(), B.min(), B.max()), cmap='turbo',
                       vmin=clim[0] if clim else None, vmax=clim[1] if clim else None, interpolation='nearest')
        plt.colorbar(im, ax=ax, shrink=0.6, label='xyz'[k])
    else:
        img[ib[o], ia[o]] = np.abs(n[o, k]) * 0.8 + 0.2
        ax.imshow(img, origin='lower', extent=(A.min(), A.max(), B.min(), B.max()), cmap='gray', vmin=0, vmax=1,
                  interpolation='nearest')
    ax.set_title(f'from {view}'); ax.set_xlabel('xyz'[i]); ax.set_ylabel('xyz'[j])
    ax.grid(True, alpha=0.3); ax.tick_params(labelsize=7)


def render_iso(ax, p, n, view, px):
    v = np.array(ISO[view], float); v /= np.linalg.norm(v)
    up = np.array([0, 0, 1.0]); up -= up @ v * v; up /= np.linalg.norm(up)
    r = np.cross(up, v)
    a, b, dep = p @ r, p @ up, p @ v
    ia = ((a - a.min()) / px).astype(int); ib = ((b.max() - b) / px).astype(int)
    img = np.full((ib.max() + 1, ia.max() + 1), np.nan)
    o = np.argsort(dep)
    L = v + 0.5 * up; L /= np.linalg.norm(L)
    img[ib[o], ia[o]] = np.abs(n[o] @ L) * 0.8 + 0.2
    ax.imshow(img, cmap='gray', vmin=0, vmax=1, interpolation='nearest'); ax.set_title(view); ax.axis('off')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cloud'); ap.add_argument('out')
    ap.add_argument('--kind', choices=['depth', 'shaded'], default='depth')
    ap.add_argument('--views', default='+z,-z,+y,-y,+x,-x')
    ap.add_argument('--px', type=float, default=0.35)
    ap.add_argument('--where')
    ap.add_argument('--clim')
    ap.add_argument('--dpi', type=int, default=55)
    a = ap.parse_args()
    d = load_cloud(a.cloud)
    d = d[mask(d, a.where)]
    p, n = d[:, :3], d[:, 3:6]
    views = a.views.split(',')
    clim = tuple(map(float, a.clim.split(','))) if a.clim else None
    cols = min(3, len(views)); rows = (len(views) + cols - 1) // cols
    fig, axs = plt.subplots(rows, cols, figsize=(7 * cols, 6 * rows)); axs = np.atleast_1d(axs).ravel()
    for ax, v in zip(axs, views):
        if v in AX:
            render_axis(ax, p, n, v, a.kind, a.px, clim)
        else:
            render_iso(ax, p, n, v, a.px)
    for ax in axs[len(views):]:
        ax.axis('off')
    plt.tight_layout(); plt.savefig(out_path(a.out), dpi=a.dpi)
    print('wrote', a.out)


if __name__ == '__main__':
    main()
