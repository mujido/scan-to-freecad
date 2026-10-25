"""FreeCAD PartDesign helpers for spreadsheet-driven, fully constrained reverse-engineered models.

Use inside FreeCAD (GUI via MCP bridge, or freecadcmd):

    import sys; sys.path.insert(0, r'<skill>/scripts')
    import importlib, fc_builder; importlib.reload(fc_builder)
    from fc_builder import make_params, Builder, report

    doc = App.newDocument('part')
    make_params(doc, [('Envelope', None, '', ''), ('CylR', 13.05, 'mm', 'outer radius'), ...])
    b = Builder(doc, 'Part')              # second variant: Builder(doc, 'PartPrint', suffix='_P')
    P = b.P                                # 'Params.' - prefix for expressions
    b.prim('AdditiveCylinder', 'Outer', {'Radius': f'{P}CylR', 'Height': '100 mm'}, ('-50 mm', '0 mm', '0 mm'), (0, 1, 0), '90 deg')
    sk = b.sketch('SlotSketch', b.YZ, ('0 mm', f'{P}SlotZ', f'{P}SlotX'))
    b.polygon(sk, [(f'-{P}SlotHW', '0 mm'), (f'{P}SlotHW', '0 mm'), (f'{P}SlotHW', '30 mm'), (f'-{P}SlotHW', '30 mm')])
    b.pocket('Slot', sk, through=True, direction=(1, 0, 0))
    b.finish(); doc.recompute(); report(b.body)

Conventions worth knowing (see references/freecad-pitfalls.md):
  * Sketch on XY: u=X v=Y normal +Z.  XZ: u=X v=Z normal -Y.  YZ: u=Y v=Z normal +X.
    AttachmentOffset.Base is in sketch coordinates (u, v, along-normal).
  * Pockets cut opposite the sketch normal unless reversed; passing direction=(...) sets a custom vector, which is
    the least surprising option.
  * Every helper seeds geometry and constraints with the evaluated expression values, so the solver starts at the
    answer and never flips an arc or a crossing.
"""
import math

import FreeCAD as App
import Part
import Sketcher


def make_params(doc, rows, name='Params'):
    """rows: (alias, value, unit, note); value None makes a section header row.
    Keep this to the knobs a user will tune (fit, hardware, printing, strength); pass measured shape values as
    literal expressions (e.g. '13.05 mm') or build-script constants instead of sheet cells."""
    sh = doc.getObject(name) or doc.addObject('Spreadsheet::Sheet', name)
    sh.set('A1', 'Parameter'); sh.set('B1', 'Value'); sh.set('C1', 'Notes')
    r = 2
    for alias, val, unit, note in rows:
        sh.set(f'A{r}', alias)
        if val is not None:
            sh.set(f'B{r}', f'={val}{unit}' if unit else f'{val}')
            sh.setAlias(f'B{r}', alias)
            sh.set(f'C{r}', note)
        r += 1
    doc.recompute()
    return sh


class Builder:
    def __init__(self, doc, body_name, sheet='Params', suffix=''):
        self.doc = doc
        self.sheet = doc.getObject(sheet)
        self.P = sheet + '.'
        self.sfx = suffix
        self.body = doc.addObject('PartDesign::Body', body_name)
        roles = {o.Role: o for o in self.body.Origin.OriginFeatures}
        self.XY, self.XZ, self.YZ = roles['XY_Plane'], roles['XZ_Plane'], roles['YZ_Plane']

    # ---- expressions -------------------------------------------------------------------------------------------
    def ev(self, expr):
        """Numeric value of an expression (mm or deg), used to seed geometry."""
        q = self.sheet.evalExpression(str(expr))
        return float(getattr(q, 'Value', q))

    @staticmethod
    def expr(obj, prop, e):
        obj.setExpression(prop, str(e))

    # ---- features ----------------------------------------------------------------------------------------------
    def prim(self, kind, name, size, base, rot_axis=None, rot_angle=None):
        """PartDesign primitive (AdditiveBox/Cylinder, SubtractiveBox/Cylinder, ...) with expression size + placement.
        Box: Length along local X, Width local Y, Height local Z from its Placement origin. Cylinder: axis = local Z."""
        o = self.body.newObject('PartDesign::' + kind, name + self.sfx)
        for k, e in size.items():
            self.expr(o, k, e)
        for k, e in zip('xyz', base):
            self.expr(o, f'.Placement.Base.{k}', e)
        if rot_axis:
            o.Placement = App.Placement(o.Placement.Base, App.Rotation(App.Vector(*rot_axis), self.ev(rot_angle)))
            self.expr(o, '.Placement.Rotation.Angle', rot_angle)
        return o

    def sketch(self, name, plane, offset=('0 mm', '0 mm', '0 mm'), rot_angle=None, rot_axis=(1, 0, 0)):
        """Sketch attached to an origin plane. offset = (u, v, along-normal); rotation is about a sketch-local axis:
        (1,0,0) tilts the plane about its u axis, (0,0,1) spins the sketch in-plane."""
        s = self.body.newObject('Sketcher::SketchObject', name + self.sfx)
        s.AttachmentSupport = [(plane, '')]
        s.MapMode = 'FlatFace'
        for k, e in zip('xyz', offset):
            self.expr(s, f'.AttachmentOffset.Base.{k}', e)
        if rot_angle:
            s.AttachmentOffset = App.Placement(s.AttachmentOffset.Base, App.Rotation(App.Vector(*rot_axis), self.ev(rot_angle)))
            self.expr(s, '.AttachmentOffset.Rotation.Angle', rot_angle)
        return s

    def pocket(self, name, sk, length=None, through=False, direction=None, reversed_=False, taper=None):
        return self._extrude('Pocket', name, sk, length, through, direction, reversed_, taper)

    def pad(self, name, sk, length=None, direction=None, reversed_=False, taper=None):
        return self._extrude('Pad', name, sk, length, False, direction, reversed_, taper)

    def _extrude(self, kind, name, sk, length, through, direction, reversed_, taper):
        f = self.body.newObject('PartDesign::' + kind, name + self.sfx)
        f.Profile = sk
        if through:
            f.Type = 'ThroughAll'
        else:
            f.Type = 'Length'
            self.expr(f, 'Length', length)
        if direction:
            f.UseCustomVector = True
            f.Direction = App.Vector(*direction)
        f.Reversed = reversed_
        if taper is not None:
            self.expr(f, 'TaperAngle', taper)
        sk.Visibility = False
        return f

    def mirror(self, name, originals, plane=None):
        """Mirror features across an origin plane (default XZ). Mirror pockets/pads from sketches; for rotated
        primitives build the second copy explicitly instead (mirroring them can corrupt later features)."""
        m = self.body.newObject('PartDesign::Mirrored', name + self.sfx)
        m.Originals = list(originals)
        m.MirrorPlane = (plane or self.XZ, [''])
        self.body.Tip = m          # Mirrored does not always become the tip; later features must build on it
        return m

    def finish(self, show=True):
        """Hide sketches and intermediate features; with show=True make this body (at its tip) the visible one."""
        for o in self.body.Group:
            if o.isDerivedFrom('Sketcher::SketchObject') or (o.isDerivedFrom('PartDesign::Feature') and o != self.body.Tip):
                o.Visibility = False
        if show:
            for b in self.doc.Objects:
                if b.isDerivedFrom('PartDesign::Body'):
                    b.Visibility = b is self.body
            self.body.Tip.Visibility = True

    # ---- sketch geometry (all fully constrained, every dimension an expression) ----------------------------------
    def _pin(self, s, geo, pos, ex, ey):
        C = Sketcher.Constraint
        i = s.addConstraint(C('DistanceX', -1, 1, geo, pos, self.ev(ex))); s.setExpression(f'Constraints[{i}]', ex)
        i = s.addConstraint(C('DistanceY', -1, 1, geo, pos, self.ev(ey))); s.setExpression(f'Constraints[{i}]', ey)

    def polygon(self, s, pts):
        """Closed polygon; pts = [(u_expr, v_expr), ...] in order. Each vertex pinned to the sketch origin."""
        V = App.Vector
        xy = [(self.ev(u), self.ev(v)) for u, v in pts]
        n = len(pts)
        g0 = s.GeometryCount
        for i in range(n):
            (x1, y1), (x2, y2) = xy[i], xy[(i + 1) % n]
            s.addGeometry(Part.LineSegment(V(x1, y1, 0), V(x2, y2, 0)))
        for i in range(n):
            s.addConstraint(Sketcher.Constraint('Coincident', g0 + i, 2, g0 + (i + 1) % n, 1))
        for i, (u, v) in enumerate(pts):
            self._pin(s, g0 + i, 1, u, v)

    def circle(self, s, cu, cv, d):
        g = s.addGeometry(Part.Circle(App.Vector(self.ev(cu), self.ev(cv), 0), App.Vector(0, 0, 1), self.ev(d) / 2))
        self._pin(s, g, 3, cu, cv)
        i = s.addConstraint(Sketcher.Constraint('Diameter', g, self.ev(d))); s.setExpression(f'Constraints[{i}]', d)

    def u_profile(self, s, hw, r, top):
        """U channel: walls at u=+-hw, circular floor of radius r touching v=0 at u=0, closed at v=top. r >= hw.
        Place the floor point with the sketch offset; extrude along the channel."""
        V, C = App.Vector, Sketcher.Constraint
        H, R, T = self.ev(hw), self.ev(r), self.ev(top)
        b = math.acos(min(1.0, H / R))
        yb = R - math.sqrt(max(R * R - H * H, 0))
        circ = Part.Circle(V(0, R, 0), V(0, 0, 1), R)
        g0 = s.addGeometry(Part.ArcOfCircle(circ, math.pi + b, 2 * math.pi - b))
        g1 = s.addGeometry(Part.LineSegment(V(H, yb, 0), V(H, T, 0)))
        g2 = s.addGeometry(Part.LineSegment(V(H, T, 0), V(-H, T, 0)))
        g3 = s.addGeometry(Part.LineSegment(V(-H, T, 0), V(-H, yb, 0)))
        for c in [C('Coincident', g0, 2, g1, 1), C('Coincident', g1, 2, g2, 1), C('Coincident', g2, 2, g3, 1),
                  C('Coincident', g3, 2, g0, 1), C('Vertical', g1), C('Vertical', g3), C('Horizontal', g2),
                  C('PointOnObject', g0, 3, -2)]:
            s.addConstraint(c)
        for e, c in [(r, C('Radius', g0, R)), (r, C('DistanceY', -1, 1, g0, 3, R)), (hw, C('DistanceX', -1, 1, g1, 1, H)),
                     (f'-({hw})', C('DistanceX', -1, 1, g3, 2, -H)), (top, C('DistanceY', -1, 1, g2, 1, T))]:
            i = s.addConstraint(c); s.setExpression(f'Constraints[{i}]', e)

    def rounded_rect(self, s, u0, u1, v0, v1, r):
        """Rectangle u0..u1 x v0..v1 with tangent corner arcs of radius r (arc centres pinned)."""
        V, C = App.Vector, Sketcher.Constraint
        U0, U1, V0, V1, R = (self.ev(e) for e in (u0, u1, v0, v1, r))
        corners = [((U0 + R, V0 + R), 180), ((U1 - R, V0 + R), 270), ((U1 - R, V1 - R), 0), ((U0 + R, V1 - R), 90)]
        g = []
        for (cx, cy), a in corners:
            g.append(s.addGeometry(Part.ArcOfCircle(Part.Circle(V(cx, cy, 0), V(0, 0, 1), R), math.radians(a), math.radians(a + 90))))
            g.append(None)
        for k in range(4):
            g[2 * k + 1] = s.addGeometry(Part.LineSegment(s.getPoint(g[2 * k], 2), s.getPoint(g[(2 * k + 2) % 8], 1)))
        for k in range(8):
            s.addConstraint(C('Tangent', g[k], 2, g[(k + 1) % 8], 1))
        cexpr = [(f'{u0} + {r}', f'{v0} + {r}'), (f'{u1} - {r}', f'{v0} + {r}'), (f'{u1} - {r}', f'{v1} - {r}'), (f'{u0} + {r}', f'{v1} - {r}')]
        for k, (ex, ey) in enumerate(cexpr):
            self._pin(s, g[2 * k], 3, ex, ey)
            i = s.addConstraint(C('Radius', g[2 * k], R)); s.setExpression(f'Constraints[{i}]', r)

    def teardrop(self, s, d):
        """Circle of diameter d centred on the sketch origin with a 90 deg point along sketch +v. Spin the sketch
        (rot_axis=(0,0,1)) so +v points up in the print orientation; then horizontal holes print without support."""
        V, C = App.Vector, Sketcher.Constraint
        r = self.ev(d) / 2; k = r / math.sqrt(2)
        arc = s.addGeometry(Part.ArcOfCircle(Part.Circle(V(0, 0, 0), V(0, 0, 1), r), math.radians(135), math.radians(405)))
        l1 = s.addGeometry(Part.LineSegment(V(k, k, 0), V(0, r * math.sqrt(2), 0)))
        l2 = s.addGeometry(Part.LineSegment(V(0, r * math.sqrt(2), 0), V(-k, k, 0)))
        for c in [C('Coincident', arc, 3, -1, 1), C('Tangent', arc, 2, l1, 1), C('Coincident', l1, 2, l2, 1),
                  C('Tangent', l2, 2, arc, 1), C('PointOnObject', l1, 2, -2)]:
            s.addConstraint(c)
        i = s.addConstraint(C('Diameter', arc, 2 * r)); s.setExpression(f'Constraints[{i}]', d)
        i = s.addConstraint(C('DistanceY', -1, 1, l1, 2, r * math.sqrt(2))); s.setExpression(f'Constraints[{i}]', f'({d}) / 2 * sqrt(2)')


def report(body):
    """Print status of every feature and sketch; read this after every rebuild."""
    ok = True
    for o in body.Group:
        if o.isDerivedFrom('Sketcher::SketchObject'):
            fc = getattr(o, 'FullyConstrained', '?')
            st = o.solve()
            ok &= (st == 0)
            print(f'  {o.Name:28s} sketch solve={st} fully_constrained={fc}')
        elif o.isDerivedFrom('PartDesign::Feature'):
            bad = any(s in ('Invalid', 'Error') for s in o.State) or not o.Shape.isValid()
            ok &= not bad
            print(f'  {o.Name:28s} {"ERROR " + str(o.State) if bad else "ok":6s} vol={o.Shape.Volume:10.1f}')
    shp = body.Shape
    print(f'{body.Name}: valid={shp.isValid()} solids={len(shp.Solids)} volume={shp.Volume:.1f} bbox={shp.optimalBoundingBox()}')
    return ok and shp.isValid() and len(shp.Solids) == 1


def flex_test(doc, body, changes):
    """changes: {alias: new_value_string}. Applies each, recomputes, checks validity, restores originals."""
    sh = next(o for o in doc.Objects if o.TypeId == 'Spreadsheet::Sheet')
    orig = {a: sh.getContents(sh.getCellFromAlias(a)) for a in changes}
    for a, v in changes.items():
        sh.set(sh.getCellFromAlias(a), v); doc.recompute()
        print(f'  {a} -> {v}: valid={body.Shape.isValid()} solids={len(body.Shape.Solids)} vol={body.Shape.Volume:.1f}')
    for a, v in orig.items():
        sh.set(sh.getCellFromAlias(a), v)
    doc.recompute()
    print(f'  restored: valid={body.Shape.isValid()} vol={body.Shape.Volume:.1f}')
