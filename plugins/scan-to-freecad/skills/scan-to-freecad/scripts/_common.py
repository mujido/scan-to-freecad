"""Shared helpers for the scan-to-freecad scripts (numpy / scipy only)."""
import json
import os
import struct

import numpy as np


def load_cloud(path):
    """Cloud saved by pcload.py / align.py: float32 array N x 6 (x y z nx ny nz)."""
    d = np.load(path)
    if d.ndim != 2 or d.shape[1] < 3:
        raise SystemExit(f'{path}: expected an N x 6 array from pcload.py')
    if d.shape[1] < 6:
        d = np.hstack([d[:, :3], np.zeros((len(d), 3), d.dtype)])
    return d.astype(np.float64)


def read_stl(path):
    with open(path, 'rb') as f:
        data = f.read()
    if data[:5].lower() == b'solid' and b'facet' in data[:2000]:
        pts = [list(map(float, l.split()[1:4])) for l in data.decode('ascii', 'ignore').splitlines()
               if l.strip().startswith('vertex')]
        tri = np.array(pts).reshape(-1, 3, 3)
    else:
        n = struct.unpack('<I', data[80:84])[0]
        rec = np.frombuffer(data[84:84 + n * 50], dtype=np.dtype([('n', '<f4', 3), ('v', '<f4', (3, 3)), ('a', '<u2')]))
        tri = rec['v'].astype(np.float64)
    v, f = np.unique(tri.reshape(-1, 3).round(6), axis=0, return_inverse=True)
    return v, f.reshape(-1, 3)


def load_mesh(path):
    """Mesh as (vertices, faces). Accepts .npz from fc_export.py (keys v, f) or .stl."""
    if path.lower().endswith('.stl'):
        return read_stl(path)
    z = np.load(path)
    return z['v'].astype(np.float64), z['f'].astype(np.int64)


def apply_transform(points, T, normals=None):
    T = np.asarray(T, float)
    p = points @ T[:3, :3].T + T[:3, 3]
    if normals is None:
        return p
    return p, normals @ T[:3, :3].T


def load_transform(path):
    if not path:
        return None
    with open(path) as f:
        return np.array(json.load(f)['matrix'], float)


def save_transform(path, T, **extra):
    with open(path, 'w') as f:
        json.dump({'matrix': np.asarray(T).tolist(), **extra}, f, indent=1)


def sample_mesh(v, f, n=1_000_000, seed=0):
    """Area-weighted random surface samples and their face normals."""
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    fn = np.cross(b - a, c - a)
    area = np.linalg.norm(fn, axis=1) / 2
    fn /= np.maximum(2 * area, 1e-12)[:, None]
    rng = np.random.default_rng(seed)
    i = rng.choice(len(f), n, p=area / area.sum())
    r1, r2 = rng.random(n), rng.random(n)
    s = np.sqrt(r1)
    q = (1 - s)[:, None] * a[i] + (s * (1 - r2))[:, None] * b[i] + (s * r2)[:, None] * c[i]
    return q, fn[i]


def wrap_terms(expr):
    """Parenthesise each top-level term around & and |, so "z>1 & nz>0.9" means (z>1) & (nz>0.9)
    (in plain Python, & binds tighter than >)."""
    out, depth, term = [], 0, ''
    for ch in expr:
        depth += ch == '('
        depth -= ch == ')'
        if ch in '&|' and depth == 0:
            out += [f'({term.strip()})', ch]
            term = ''
        else:
            term += ch
    out.append(f'({term.strip()})')
    return ' '.join(out)


def mask(d, expr):
    """Evaluate a selection like "x>-27 & x<-9 & abs(y)<7.4 & nz>0.2" on an N x 6 cloud."""
    if not expr:
        return np.ones(len(d), bool)
    expr = wrap_terms(expr)
    env = {'x': d[:, 0], 'y': d[:, 1], 'z': d[:, 2], 'nx': d[:, 3], 'ny': d[:, 4], 'nz': d[:, 5],
           'r_xy': np.hypot(d[:, 0], d[:, 1]), 'r_yz': np.hypot(d[:, 1], d[:, 2]), 'r_xz': np.hypot(d[:, 0], d[:, 2]),
           'abs': np.abs, 'np': np}
    m = eval(expr, {'__builtins__': {}}, env)
    return np.asarray(m, bool)


def out_path(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    return path
