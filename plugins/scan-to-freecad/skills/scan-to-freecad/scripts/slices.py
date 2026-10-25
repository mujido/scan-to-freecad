"""Cross-sections of the scan (black points), optionally overlaid with model sections.

--axis x|y|z  --levels="-30,-20,0,10"   (use = when the list starts with a minus sign)  --thick 0.25 (slab half-thickness; ~2x point spacing)
--model sections.json   red outlines (from fc_export.export_sections with the same axis/levels)
--model2 other.json     blue outlines (e.g. a user's reference model)

Example:  python slices.py aligned.npy x_slices.png --axis x --levels="-25,-15,0,15,25"
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from _common import load_cloud, out_path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cloud'); ap.add_argument('out')
    ap.add_argument('--axis', choices=['x', 'y', 'z'], required=True)
    ap.add_argument('--levels', required=True)
    ap.add_argument('--thick', type=float, default=0.25)
    ap.add_argument('--model'); ap.add_argument('--model2')
    ap.add_argument('--cols', type=int, default=4)
    ap.add_argument('--dpi', type=int, default=55)
    a = ap.parse_args()
    d = load_cloud(a.cloud); p = d[:, :3]
    k = 'xyz'.index(a.axis); o = [i for i in range(3) if i != k]
    levels = [float(v) for v in a.levels.split(',')]
    secs = [json.load(open(f)) if f else None for f in (a.model, a.model2)]
    cols = min(a.cols, len(levels)); rows = (len(levels) + cols - 1) // cols
    fig, axs = plt.subplots(rows, cols, figsize=(5 * cols, 5 * rows)); axs = np.atleast_1d(axs).ravel()
    for ax, l in zip(axs, levels):
        m = np.abs(p[:, k] - l) < a.thick
        ax.scatter(p[m, o[0]], p[m, o[1]], s=0.6, c='k')
        for sec, col in zip(secs, ('r', 'b')):
            if sec is None:
                continue
            key = next((kk for kk in sec if kk.split('_')[0] == str(k) and abs(float(kk.split('_')[1]) - l) < 1e-6), None)
            for seg in (sec.get(key) or []):
                s = np.array(seg); ax.plot(s[:, o[0]], s[:, o[1]], col + '-', lw=1)
        ax.set_aspect('equal'); ax.grid(True, alpha=0.4)
        ax.set_xlim(p[:, o[0]].min() - 1, p[:, o[0]].max() + 1); ax.set_ylim(p[:, o[1]].min() - 1, p[:, o[1]].max() + 1)
        ax.set_title(f'{a.axis}={l:g}' + ('  black=scan red=model' if secs[0] else '') + (' blue=model2' if secs[1] else ''), fontsize=9)
        ax.set_xlabel('xyz'[o[0]]); ax.set_ylabel('xyz'[o[1]])
    for ax in axs[len(levels):]:
        ax.axis('off')
    plt.tight_layout(); plt.savefig(out_path(a.out), dpi=a.dpi)
    print('wrote', a.out)


if __name__ == '__main__':
    main()
