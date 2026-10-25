"""FreeCAD-side export and probing helpers (import inside FreeCAD).

    import sys; sys.path.insert(0, r'<skill>/scripts'); import fc_export as fx
    fx.export_mesh(doc.Part.Shape, r'<scratch>/model.npz')                     # for compare.py / overhang.py
    fx.export_sections(doc.Part.Shape, {'x': [-20, 0, 20], 'z': [0, 5]}, r'<scratch>/sections.json')
    fx.probe(doc.Part.Shape, [(x, y, z), ...])                                 # True = inside solid
    fx.export_files(doc.Part.Shape, r'<project>/part')                         # part.step + part.stl, checked
    fx.export_print_oriented(doc.PartPrint.Shape, bed_normal=(-0.81, 0, -0.58), path=r'<project>/part_print_oriented.stl')
    fx.screenshot(doc, ['PartPrint'], r'<project>/part.png')
    fx.place_reference(r'<user>.step', T_json, doc)                            # reference model in the scan frame

Probing with isInside on imported STEP shapes (B-spline faces) is slow - thousands of probes can freeze the GUI.
For bulk inside/outside maps export a mesh and work on it outside FreeCAD; keep probes here to a few dozen.
"""
import json
import math

import numpy as np
import FreeCAD as App
import Part


def _mesh(shape, deflection=0.02):
    import MeshPart
    return MeshPart.meshFromShape(Shape=shape, LinearDeflection=deflection, AngularDeflection=0.1, Relative=False)


def export_mesh(shape, path, deflection=0.02):
    m = _mesh(shape, deflection)
    np.savez(path, v=np.array([[p.x, p.y, p.z] for p in m.Points]), f=np.array([t.PointIndices for t in m.Facets]))
    return path


def export_sections(shape, levels, path):
    """levels: {'x': [...], 'y': [...], 'z': [...]} -> JSON readable by slices.py --model."""
    out = {}
    for ax, ls in levels.items():
        k = 'xyz'.index(ax)
        n = App.Vector(*np.eye(3)[k])
        for l in ls:
            out[f'{k}_{float(l)}'] = [[[p.x, p.y, p.z] for p in e.discretize(Distance=0.2)] for w in shape.slice(n, float(l)) for e in w.Edges]
    with open(path, 'w') as f:
        json.dump(out, f)
    return path


def probe(shape, points, tol=0.01):
    return [shape.isInside(App.Vector(*p), tol, True) for p in points]


def export_files(shape, stem, deflection=0.01):
    """stem.step + stem.stl; reports whether the STL is a closed solid."""
    shape.exportStep(stem + '.step')
    m = _mesh(shape, deflection)
    m.write(stem + '.stl')
    print(f'{stem}: STL solid={m.isSolid()} non-manifold={m.hasNonManifolds()} volume={m.Volume:.1f}')
    return m.isSolid() and not m.hasNonManifolds()


def export_print_oriented(shape, bed_normal, path, deflection=0.01):
    """Rotate so the face with outward normal bed_normal lies on Z=0, centre in XY, write STL."""
    o = shape.copy()
    o.Placement = App.Placement(App.Vector(), App.Rotation(App.Vector(*bed_normal), App.Vector(0, 0, -1)))
    o = o.copy()
    bb = o.optimalBoundingBox()
    o.translate(App.Vector(-(bb.XMin + bb.XMax) / 2, -(bb.YMin + bb.YMax) / 2, -bb.ZMin))
    m = _mesh(o, deflection); m.write(path)
    bed = sum(f.Area for f in o.Faces if f.BoundBox.ZMax < 1e-3)
    print(f'{path}: height {o.optimalBoundingBox().ZLength:.1f}  bed contact {bed:.1f} mm2  solid={m.isSolid()}')
    return o


def place_reference(step_path, transform_json, doc, name='Reference'):
    """Load a reference STEP and move it into the scan frame with a rigid Placement (keeps booleans working)."""
    T = np.array(json.load(open(transform_json))['matrix'], float)
    U, _, Vt = np.linalg.svd(T[:3, :3]); T[:3, :3] = U @ Vt          # re-orthonormalise
    s = Part.Shape(); s.read(step_path)
    solid = (s.Solids[0] if s.Solids else s).copy()
    solid.Placement = App.Placement(App.Matrix(*T.ravel().tolist()))
    obj = doc.getObject(name) or doc.addObject('Part::Feature', name)
    obj.Shape = solid
    doc.recompute()
    return obj


def screenshot(doc, visible, path, view='iso', size=(1000, 700)):
    """Small PNG with only the named objects visible (GUI only). Restores visibility afterwards."""
    import FreeCADGui as Gui
    v = Gui.getDocument(doc.Name).ActiveView
    before = {o.Name: o.Visibility for o in doc.Objects if hasattr(o, 'Visibility')}
    for o in doc.Objects:
        if o.isDerivedFrom('PartDesign::Body') or o.TypeId == 'Part::Feature':
            o.Visibility = o.Name in visible
    getattr(v, {'iso': 'viewIsometric', 'front': 'viewFront', 'top': 'viewTop', 'right': 'viewRight',
                'rear': 'viewRear', 'bottom': 'viewBottom', 'left': 'viewLeft'}[view])()
    v.fitAll()
    v.saveImage(path, size[0], size[1], 'White')
    for n, vis in before.items():
        o = doc.getObject(n)
        if o is not None:
            o.Visibility = vis
    return path
