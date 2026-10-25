"""Load a scan into cloud.npy (float32 N x 6: x y z nx ny nz).

Formats: PLY (ascii, binary little/big endian; vertex properties in any order, faces ignored),
ASC/XYZ/TXT/CSV (whitespace or comma separated; --cols picks columns), PCD (ascii), STL (vertices).
Normals come from the file when present; otherwise they are estimated (PCA over k nearest neighbours,
oriented away from the cloud centre - check them before trusting inward/outward tests).

Example:  python pcload.py scan.ply out/cloud.npy
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from _common import out_path, read_stl

TYPES = {'char': 'i1', 'uchar': 'u1', 'short': 'i2', 'ushort': 'u2', 'int': 'i4', 'uint': 'u4', 'float': 'f4', 'double': 'f8',
         'int8': 'i1', 'uint8': 'u1', 'int16': 'i2', 'uint16': 'u2', 'int32': 'i4', 'uint32': 'u4', 'float32': 'f4', 'float64': 'f8'}


def read_ply(path):
    with open(path, 'rb') as f:
        header = []
        while True:
            line = f.readline()
            if not line:
                raise SystemExit('PLY header has no end_header')
            line = line.decode('ascii', 'ignore').strip()
            header.append(line)
            if line == 'end_header':
                break
        fmt = next(l.split()[1] for l in header if l.startswith('format'))
        elements, cur = [], None
        for l in header:
            t = l.split()
            if t[0] == 'element':
                cur = {'name': t[1], 'n': int(t[2]), 'props': []}
                elements.append(cur)
            elif t[0] == 'property' and cur is not None:
                cur['props'].append(('list', t[2], t[3], t[4]) if t[1] == 'list' else (t[1], t[2]))
        vert = next(e for e in elements if e['name'] == 'vertex')
        if any(p[0] == 'list' for p in vert['props']):
            raise SystemExit('list properties on vertices are not supported')
        names = [p[1] for p in vert['props']]
        if fmt == 'ascii':
            for e in elements:          # vertices are usually first; skip any elements before them
                if e is vert:
                    break
                for _ in range(e['n']):
                    f.readline()
            a = np.loadtxt(f, max_rows=vert['n'], dtype=np.float64, ndmin=2)
            cols = {n: a[:, i] for i, n in enumerate(names)}
        else:
            end = '<' if 'little' in fmt else '>'
            dt = np.dtype([(p[1], end + TYPES[p[0]]) for p in vert['props']])
            for e in elements:
                if e is vert:
                    break
                raise SystemExit('binary PLY with elements before vertex is not supported')
            rec = np.frombuffer(f.read(vert['n'] * dt.itemsize), dt, vert['n'])
            cols = {n: rec[n].astype(np.float64) for n in names}
    xyz = np.stack([cols['x'], cols['y'], cols['z']], 1)
    nrm = np.stack([cols['nx'], cols['ny'], cols['nz']], 1) if all(k in cols for k in ('nx', 'ny', 'nz')) else None
    return xyz, nrm


def read_text(path, cols):
    with open(path, 'r', errors='ignore') as f:
        lines = [l.replace(',', ' ').split() for l in f]
    rows = []
    for t in lines:
        try:
            rows.append([float(v) for v in t])
        except ValueError:
            continue                    # header / comment lines
    width = min(len(r) for r in rows if len(r) >= 3)
    a = np.array([r[:width] for r in rows if len(r) >= width])
    if cols:
        idx = [int(c) for c in cols.split(',')]
        xyz = a[:, idx[:3]]
        return xyz, (a[:, idx[3:6]] if len(idx) >= 6 else None)
    xyz = a[:, :3]
    for start in (3, 6, 4):             # common layouts: xyz n | xyz rgb n | xyz i n
        if a.shape[1] >= start + 3:
            n = a[:, start:start + 3]
            if np.allclose(np.linalg.norm(n[:1000], axis=1), 1, atol=0.05):
                return xyz, n
    return xyz, None


def read_pcd(path):
    with open(path, 'r', errors='ignore') as f:
        lines = f.read().splitlines()
    fields, i = None, 0
    for i, l in enumerate(lines):
        if l.startswith('FIELDS'):
            fields = l.split()[1:]
        if l.startswith('DATA'):
            if 'ascii' not in l:
                raise SystemExit('only ascii PCD is supported')
            break
    a = np.loadtxt(lines[i + 1:], ndmin=2)
    c = {n: a[:, k] for k, n in enumerate(fields)}
    xyz = np.stack([c['x'], c['y'], c['z']], 1)
    nk = ('normal_x', 'normal_y', 'normal_z')
    return xyz, (np.stack([c[k] for k in nk], 1) if all(k in c for k in nk) else None)


def estimate_normals(xyz, k=16):
    from scipy.spatial import cKDTree
    t = cKDTree(xyz)
    n = np.empty_like(xyz)
    for s in range(0, len(xyz), 200_000):
        _, idx = t.query(xyz[s:s + 200_000], k)
        nb = xyz[idx] - xyz[idx].mean(1, keepdims=True)
        w, v = np.linalg.eigh(np.einsum('nki,nkj->nij', nb, nb))
        n[s:s + 200_000] = v[:, :, 0]
    flip = np.einsum('ij,ij->i', n, xyz - xyz.mean(0)) < 0
    n[flip] *= -1
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('scan')
    ap.add_argument('out', help='output .npy')
    ap.add_argument('--cols', help='text formats: comma list of column indices "x,y,z[,nx,ny,nz]"')
    ap.add_argument('--estimate-normals', action='store_true', help='recompute normals even if the file has them')
    ap.add_argument('--scale', type=float, default=1.0, help='multiply coordinates (e.g. 1000 for metres -> mm)')
    a = ap.parse_args()
    ext = os.path.splitext(a.scan)[1].lower()
    if ext == '.ply':
        xyz, n = read_ply(a.scan)
    elif ext == '.pcd':
        xyz, n = read_pcd(a.scan)
    elif ext == '.stl':
        xyz, _ = read_stl(a.scan)
        n = None
    else:
        xyz, n = read_text(a.scan, a.cols)
    xyz = xyz * a.scale
    if n is None or a.estimate_normals:
        print('estimating normals ...')
        n = estimate_normals(xyz)
    n = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    np.save(out_path(a.out), np.hstack([xyz, n]).astype(np.float32))
    lo, hi = xyz.min(0), xyz.max(0)
    print(f'{len(xyz)} points  min {np.round(lo, 2)}  max {np.round(hi, 2)}  size {np.round(hi - lo, 2)}')
    from scipy.spatial import cKDTree
    sub = xyz[np.random.default_rng(0).choice(len(xyz), min(2000, len(xyz)), replace=False)]
    nn = cKDTree(xyz).query(sub, 2)[0][:, 1]
    print(f'typical point spacing ~{np.median(nn):.3f} (use ~2x this as slice thickness)')


if __name__ == '__main__':
    main()
