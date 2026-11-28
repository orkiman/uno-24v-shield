"""Build hardware/uno-24v-shield.kicad_pcb from the EasyEDA v5 layout.

  1. import the EasyEDA Pro backup with KiCad's own importer
  2. export every used footprint (normalised, cleaned) to lib/uno24v.pretty
  3. create a fresh KiCad board, place library footprints exactly where the
     v5 parts were, assign v6 nets from design.py
  4. copy v5 copper (tracks/vias) with nets renamed; drop copper that only
     served removed parts; prune dangling stubs
  5. v6 copper edits (see EDITS below), zones, silkscreen, rules
"""
import math
import os
import sys

import pcbnew

import design
import gen_schematic
import kicadlib
import lcsc_fp

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, 'source', 'easyeda', 'uno-glue-controller-single-fet-231125_backup-2025-11-30.epro')
HW = kicadlib.PROJ
PCB = os.path.join(HW, 'uno-24v-shield.kicad_pcb')
FPLIB = os.path.join(HW, 'lib', 'uno24v.pretty')
MM = 1e6
D2S = {}  # design net name -> schematic net name


def mm(v):
    return int(round(v * MM))


def P(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


KEEP_FP_LAYERS = {pcbnew.F_SilkS, pcbnew.F_Fab, pcbnew.F_CrtYd, pcbnew.B_SilkS, pcbnew.B_Fab, pcbnew.B_CrtYd}


def import_v5():
    io = pcbnew.PCB_IO_MGR.PluginFind(pcbnew.PCB_IO_MGR.EASYEDAPRO)
    return io.LoadBoard(SRC, None)


def normalise_fp(f):
    """in place: footprint -> library form (origin, 0 deg, cleaned layers)"""
    fp = f
    f.SetOrientationDegrees(0)
    f.SetPosition(pcbnew.VECTOR2I(0, 0))
    for pad in f.Pads():
        pad.SetNetCode(0)
    for fld in list(f.GetFields()):
        if fld.GetName().startswith('JLC_'):
            f.RemoveField(fld.GetName())
    f.Models().clear()
    name = str(fp.GetFPID().GetLibItemName())
    f.SetFPID(pcbnew.LIB_ID('uno24v', name))
    ref = f.Reference()
    ref.SetText('REF**')
    ref.SetLayer(pcbnew.F_Fab)
    ref.SetVisible(True)
    ref.SetTextSize(P(0.6, 0.6))
    ref.SetTextThickness(mm(0.1))
    val = f.Value()
    val.SetText(name)
    val.SetLayer(pcbnew.F_Fab)
    val.SetVisible(False)
    tht = any(p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH for p in f.Pads())
    f.SetAttributes(pcbnew.FP_THROUGH_HOLE if tht else pcbnew.FP_SMD)
    return name, f


def build_fp_lib(old):
    """write lib/uno24v.pretty/*.kicad_mod (via a scratch board, since the
    KiCad 9 python API cannot create footprint libraries directly)"""
    import shutil
    import tempfile
    import sexp
    wanted = {}
    for p in design.PARTS.values():
        if not p['old'] or p['ref'] in design.LCSC_FOOTPRINTS or p['ref'] in PAD_ANCHOR:
            continue
        fp = old.FindFootprintByReference(p['old'])
        if str(fp.GetFPID().GetLibItemName()) in wanted:
            continue
        old.Remove(fp)
        name, f = normalise_fp(fp)
        assert name == p['fp'], (p['ref'], name, p['fp'])
        wanted[name] = f
    tmpd = tempfile.mkdtemp()
    tb = pcbnew.NewBoard(os.path.join(tmpd, 'fp.kicad_pcb'))
    for f in wanted.values():
        tb.Add(f)
    pcbnew.SaveBoard(os.path.join(tmpd, 'fp.kicad_pcb'), tb)
    tree = sexp.parse(open(os.path.join(tmpd, 'fp.kicad_pcb'), encoding='utf-8').read())
    shutil.rmtree(tmpd)
    if os.path.isdir(FPLIB):
        shutil.rmtree(FPLIB)
    os.makedirs(FPLIB)
    for fe in sexp.find(tree, 'footprint'):
        name = fe[1].split(':', 1)[1]
        fe[1] = name
        drop = ('at', 'uuid', 'path', 'sheetname', 'sheetfile')
        body = [x for x in fe[2:] if not (isinstance(x, list) and x and x[0] in drop)]
        out = ['footprint', name, ['version', 20241229], ['generator', 'pcbnew'],
               ['generator_version', '9.0']] + [x for x in body if not (isinstance(x, list) and x[0] in ('version', 'generator', 'generator_version'))]

        keep = {'F.SilkS', 'F.Fab', 'F.CrtYd', 'B.SilkS', 'B.Fab', 'B.CrtYd'}
        gr = ('fp_line', 'fp_rect', 'fp_circle', 'fp_arc', 'fp_poly', 'fp_curve', 'fp_text')

        def on_kept_layer(x):
            if not (isinstance(x, list) and x and x[0] in gr):
                return True
            lay = sexp.find1(x, 'layer')
            return lay is not None and str(lay[1]) in keep
        out = [x for x in out if on_kept_layer(x)]

        def strip_uuid(e):
            return [strip_uuid(x) if isinstance(x, list) else x for x in e
                    if not (isinstance(x, list) and x and x[0] == 'uuid')]
        out = strip_uuid(out)
        with open(os.path.join(FPLIB, name + '.kicad_mod'), 'w', encoding='utf-8') as fh:
            fh.write(sexp.dump(out) + '\n')
    assert len(os.listdir(FPLIB)) == len(wanted)
    with open(os.path.join(FPLIB, 'F1812.kicad_mod'), 'w', encoding='utf-8') as fh:
        fh.write(F1812)
    for ref, code in design.LCSC_FOOTPRINTS.items():
        name = design.PARTS[ref]['fp']
        with open(os.path.join(FPLIB, name + '.kicad_mod'), 'w', encoding='utf-8') as fh:
            fh.write(lcsc_fp.kicad_mod(code, name))


# 1812 resettable fuse, pad geometry from the LCSC footprint of C19723490
F1812 = '''(footprint "F1812"
	(version 20241229)
	(generator "uno24v_scripts")
	(layer "F.Cu")
	(descr "1812 resettable fuse, pads per LCSC F1812 (C19723490)")
	(attr smd)
	(property "Reference" "REF**" (at 0 -2.8 0) (layer "F.Fab") (effects (font (size 0.6 0.6) (thickness 0.1))))
	(property "Value" "F1812" (at 0 2.8 0) (layer "F.Fab") (hide yes) (effects (font (size 0.6 0.6) (thickness 0.1))))
	(fp_line (start -2.794 -1.78) (end -2.794 1.78) (stroke (width 0.152) (type solid)) (layer "F.SilkS"))
	(fp_line (start 2.794 -1.78) (end 2.794 1.78) (stroke (width 0.152) (type solid)) (layer "F.SilkS"))
	(fp_line (start -1.0 -2.03) (end 1.0 -2.03) (stroke (width 0.152) (type solid)) (layer "F.SilkS"))
	(fp_line (start -1.0 2.03) (end 1.0 2.03) (stroke (width 0.152) (type solid)) (layer "F.SilkS"))
	(fp_rect (start -2.25 -1.6) (end 2.25 1.6) (stroke (width 0.1) (type solid)) (fill no) (layer "F.Fab"))
	(fp_rect (start -3.1 -2.3) (end 3.1 2.3) (stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd"))
	(pad "1" smd rect (at -1.853 0) (size 1.407 3.499) (layers "F.Cu" "F.Paste" "F.Mask"))
	(pad "2" smd rect (at 1.853 0) (size 1.407 3.499) (layers "F.Cu" "F.Paste" "F.Mask"))
)
'''


def match_place(f, old_pads, p):
    """put a (JLCPCB) footprint so that its pads sit exactly on the v5 pads,
    trying all four orientations; the pin carrying a net must land on v5
    copper of that same net (GND pins may land anywhere: their old copper
    is removed by power_edits)"""
    tol = mm(0.3)
    for deg in (0, 90, 180, 270):
        f.SetOrientationDegrees(deg)
        f.SetPosition(pcbnew.VECTOR2I(0, 0))
        local = {q.GetNumber(): q.GetPosition() for q in f.Pads()}
        anchor = sorted(local)[0]
        for op, _ in old_pads.values():
            off = op - local[anchor]
            ok = True
            for num, lp in local.items():
                hit = [(n, net) for n, (pp, net) in old_pads.items() if (lp + off - pp).EuclideanNorm() < tol]
                want = p['nets'].get(int(num))
                if not hit or (want != 'GND' and design.OLD_NET_MAP.get(hit[0][1]) != want):
                    ok = False
                    break
            if ok:
                f.SetPosition(off)
                print('  %s: JLCPCB footprint placed at %.0f deg' % (p['ref'], deg))
                return
    raise SystemExit('no pad-matching placement for ' + p['ref'])


def point_on_item(t, pt, tol, centerline=False):
    """is pt (VECTOR2I) on track/via t (within its width/2 + tol)?"""
    if t.GetClass() == 'PCB_VIA':
        return (t.GetPosition() - pt).EuclideanNorm() <= t.GetWidth(pcbnew.F_Cu) / 2 + tol
    a, b = t.GetStart(), t.GetEnd()
    ax, ay, bx, by, px, py = a.x, a.y, b.x, b.y, pt.x, pt.y
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    u = 0 if L2 == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L2))
    cx, cy = ax + u * dx, ay + u * dy
    return math.hypot(px - cx, py - cy) <= (0 if centerline else t.GetWidth() / 2) + tol


def prune_dangling(board):
    """repeatedly delete track segments with a free end and unconnected vias"""
    removed = 0
    while True:
        tracks = list(board.GetTracks())
        pads = [p for f in board.GetFootprints() for p in f.Pads()]
        dead = []
        for ti, t in enumerate(tracks):
            net = t.GetNetCode()
            if t.GetClass() == 'PCB_VIA' and t.GetNetname() == 'GND':
                continue  # stitching via between the two GND pours
            if t.GetClass() != 'PCB_VIA' and t.GetLength() < mm(0.01):
                dead.append(t)  # zero-length leftovers
                continue
            if t.GetClass() == 'PCB_VIA':
                pts = [t.GetPosition()]
            else:
                pts = [t.GetStart(), t.GetEnd()]
            for pt in pts:
                ok = False
                for p in pads:
                    if p.GetNetCode() == net and p.HitTest(pt, mm(0.01)):
                        ok = True
                        break
                if not ok:
                    for oi, o in enumerate(tracks):
                        if oi == ti or o.GetNetCode() != net:
                            continue
                        if t.GetClass() == 'PCB_VIA' and o.GetClass() == 'PCB_VIA':
                            continue
                        if o.GetClass() == 'PCB_VIA' or t.GetClass() == 'PCB_VIA' or o.GetLayer() == t.GetLayer():
                            if point_on_item(o, pt, mm(0.02), centerline=o.GetClass() != 'PCB_VIA' and t.GetClass() != 'PCB_VIA'):
                                ok = True
                                break
                if not ok:
                    dead.append(t)
                    break
            if t.GetClass() == 'PCB_VIA' and not (dead and dead[-1] is t):
                # a via needs copper on both layers (zone-stitch vias are kept separately)
                lay = set()
                for oi, o in enumerate(tracks):
                    if oi != ti and o.GetClass() != 'PCB_VIA' and o.GetNetCode() == net and point_on_item(o, t.GetPosition(), mm(0.005)):
                        lay.add(o.GetLayer())
                for p in pads:
                    if p.GetNetCode() == net and p.HitTest(t.GetPosition(), mm(0.01)):
                        lay |= {pcbnew.F_Cu, pcbnew.B_Cu}
                if len(lay) < 2 and t.GetNetname() != 'GND':
                    dead.append(t)
        if not dead:
            return removed
        for t in dead:
            board.Remove(t)
        removed += len(dead)


def add_track(board, net, layer, pts, width):
    """add a track; GND stitching vias in its way are removed (reported)"""
    n = board.FindNet(D2S.get(net, net))
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(P(x1, y1))
        t.SetEnd(P(x2, y2))
        t.SetWidth(mm(width))
        t.SetLayer(layer)
        t.SetNet(n)
        for v in list(board.GetTracks()):
            if v.GetClass() == 'PCB_VIA' and v.GetNetname() == 'GND' and point_on_item(
                    t, v.GetPosition(), v.GetWidth(pcbnew.F_Cu) / 2 + mm(0.3)):
                print('  removed GND via at (%.2f, %.2f) under new %s track' % (
                    v.GetPosition().x / MM, v.GetPosition().y / MM, net))
                board.Remove(v)
        board.Add(t)


def add_via(board, net, x, y, dia=0.61, drill=0.3):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(P(x, y))
    v.SetWidth(mm(dia))
    v.SetDrill(mm(drill))
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetNet(board.FindNet(D2S.get(net, net)))
    board.Add(v)


def schematic_nets():
    """(ref, pin) -> net name exactly as eeschema names it"""
    import subprocess
    import tempfile
    import sexp
    gen_schematic.main()
    fn = os.path.join(tempfile.mkdtemp(), 'n.net')
    subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '-o', fn,
                    os.path.join(HW, 'uno-24v-shield.kicad_sch')], check=True, capture_output=True)
    t = sexp.parse(open(fn, encoding='utf-8').read())
    out = {}
    for n in sexp.find(sexp.find1(t, 'nets'), 'net'):
        name = sexp.find1(n, 'name')[1]
        for node in sexp.find(n, 'node'):
            out[(sexp.find1(node, 'ref')[1], sexp.find1(node, 'pin')[1])] = name
    return out


def setup_rules(board):
    ds = board.GetDesignSettings()
    ds.m_MinClearance = mm(0.15)
    ds.m_TrackMinWidth = mm(0.15)
    ds.m_ViasMinSize = mm(0.55)
    ds.m_MinThroughDrill = mm(0.3)
    ds.m_ViasMinAnnularWidth = mm(0.125)
    ds.m_HoleClearance = mm(0.25)
    ds.m_HoleToHoleMin = mm(0.25)
    ds.m_CopperEdgeClearance = mm(0.3)
    ds.m_SilkClearance = mm(0)
    ds.m_MinSilkTextHeight = mm(0.7)
    ds.m_MinSilkTextThickness = mm(0.1)
    ns = ds.m_NetSettings
    dc = ns.GetDefaultNetclass()
    dc.SetClearance(mm(0.15))
    dc.SetTrackWidth(mm(0.254))
    dc.SetViaDiameter(mm(0.61))
    dc.SetViaDrill(mm(0.3))
    pw = pcbnew.NETCLASS('Power')
    pw.SetClearance(mm(0.15))
    pw.SetTrackWidth(mm(1.0))
    pw.SetViaDiameter(mm(0.9))
    pw.SetViaDrill(mm(0.45))
    ns.SetNetclass('Power', pw)
    ns.ClearNetclassPatternAssignments()
    for n in design.POWER_NETS:
        ns.SetNetclassPatternAssignment(D2S[n], 'Power')


def main():
    old = import_v5()
    place, place_pads = {}, {}
    for f in old.GetFootprints():
        place[f.GetReference()] = (f.GetPosition(), f.GetOrientation())
        place_pads[f.GetReference()] = {p.GetNumber(): (p.GetPosition(), p.GetNetname()) for p in f.Pads()}
    kicadlib.build_project_library()
    build_fp_lib(old)

    for ext in ('.kicad_pcb', '.kicad_pro', '.kicad_prl'):
        fn = PCB[:-len('.kicad_pcb')] + ext
        if os.path.exists(fn):
            os.remove(fn)
    sn = schematic_nets()
    board = pcbnew.NewBoard(PCB)
    board.SetCopperLayerCount(2)

    # nets, named exactly like the schematic netlist
    d2s = D2S
    for (ref, pin), name in sn.items():
        dn = design.PARTS[ref]['nets'].get(int(pin)) if pin.isdigit() else None
        if dn is not None:
            assert d2s.setdefault(dn, name) == name, (dn, name)
        elif not name.startswith('unconnected-'):
            sys.exit('schematic net %s on %s.%s not in design' % (name, ref, pin))
    for n in sorted(set(sn.values())):
        board.Add(pcbnew.NETINFO_ITEM(board, n))
    setup_rules(board)

    # footprints
    for ref, p in design.PARTS.items():
        if p['old']:
            pos, ori = place[p['old']]
        else:
            x, y, a = NEW_PLACEMENT[ref]
            pos, ori = P(x, y), pcbnew.EDA_ANGLE(a, pcbnew.DEGREES_T)
        f = pcbnew.FootprintLoad(FPLIB, p['fp'])
        f.SetFPID(pcbnew.LIB_ID('uno24v', p['fp']))
        board.Add(f)
        f.SetPosition(pos)
        f.SetOrientation(ori)
        if p['old'] and ref in design.LCSC_FOOTPRINTS:
            match_place(f, place_pads[p['old']], p)
        if ref in PAD_ANCHOR:
            num, deg, dx = PAD_ANCHOR[ref]
            f.SetOrientationDegrees(deg)
            target = place_pads[p['old']][num][0] + pcbnew.VECTOR2I(mm(dx), 0)
            pad = [q for q in f.Pads() if q.GetNumber() == num][0]
            f.SetPosition(f.GetPosition() + (target - pad.GetPosition()))
        f.SetReference(ref)
        f.SetValue(p['value'])
        f.Reference().SetLayer(pcbnew.F_Fab)
        for k in ('LCSC', 'MPN'):
            fld = pcbnew.PCB_FIELD(f, f.GetNextFieldId(), k)
            fld.SetText(p[k.lower()])
            fld.SetVisible(False)
            fld.SetLayer(pcbnew.F_Fab)
            f.AddField(fld)
        f.SetPath(pcbnew.KIID_PATH(gen_schematic.fp_path(ref)))
        f.SetSheetfile('uno-24v-shield.kicad_sch')
        f.SetSheetname('')
        for pad in f.Pads():
            net = sn.get((ref, pad.GetNumber()))
            if net:
                pad.SetNet(board.FindNet(net))

    # copper from v5 with renamed nets
    for t in old.GetTracks():
        on = t.GetNetname()
        if on not in design.OLD_NET_MAP:
            sys.exit('unmapped v5 net %s' % on)
        nn = design.OLD_NET_MAP[on]
        if nn is None:
            continue
        nn = d2s[nn]
        if t.GetClass() == 'PCB_VIA':
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(t.GetPosition())
            v.SetWidth(t.GetWidth(pcbnew.F_Cu))
            v.SetDrill(t.GetDrillValue())
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            v.SetNet(board.FindNet(nn))
            board.Add(v)
        else:
            assert t.GetClass() == 'PCB_TRACK', t.GetClass()
            n = pcbnew.PCB_TRACK(board)
            n.SetStart(t.GetStart())
            n.SetEnd(t.GetEnd())
            n.SetWidth(t.GetWidth())
            n.SetLayer(t.GetLayer())
            n.SetNet(board.FindNet(nn))
            board.Add(n)
    power_edits(board)
    print('pruned dangling segments:', prune_dangling(board))

    # outline + silkscreen from v5
    for d in old.GetDrawings():
        lay = d.GetLayer()
        if d.GetClass() == 'PCB_SHAPE':
            s = pcbnew.PCB_SHAPE(board)
            s.SetShape(d.GetShape())
            s.SetStart(d.GetStart())
            s.SetEnd(d.GetEnd())
            if d.GetShape() == pcbnew.SHAPE_T_ARC:
                s.SetArcGeometry(d.GetStart(), d.GetArcMid(), d.GetEnd())
            if d.GetShape() == pcbnew.SHAPE_T_POLY:
                s.SetPolyShape(d.GetPolyShape())
            s.SetFilled(d.IsFilled())
            s.SetWidth(d.GetWidth() if lay != pcbnew.Edge_Cuts else mm(0.1))
            s.SetLayer(lay)
            board.Add(s)
        elif d.GetClass() == 'PCB_TEXT':
            if lay == pcbnew.F_SilkS and d.GetText() in ('VL+', 'gnd', '24v'):
                continue  # J5 labels, replaced in add_silk()
            t = pcbnew.PCB_TEXT(board)
            txt = {'v5': 'v6', 'VL+': 'gnd', 'AD5/SCL': 'SCL', 'AD4/SDA': 'SDA'}.get(d.GetText(), d.GetText())
            ov = SILK_MOVE.get(txt) if lay == pcbnew.F_SilkS else None
            t.SetText(txt)
            t.SetLayer(lay)
            pos = d.GetPosition()
            if lay == pcbnew.B_SilkS and not d.IsMirrored() and pos.y < mm(80):
                pos = pcbnew.VECTOR2I(pos.x, pos.y + mm(2.4))
            if ov:
                pos = pcbnew.VECTOR2I(mm(ov[0]) if ov[0] else pos.x, mm(ov[1]) if ov[1] else pos.y)
            t.SetPosition(pos)
            t.SetTextAngle(d.GetTextAngle())
            t.SetHorizJustify(d.GetHorizJustify())
            t.SetVertJustify(d.GetVertJustify())
            h = max(d.GetTextHeight(), mm(0.8))
            if ov:
                h = mm(ov[2])
                t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
                t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
            t.SetTextSize(pcbnew.VECTOR2I(h, h))
            t.SetTextThickness(max(d.GetTextThickness(), mm(0.15)))
            t.SetMirrored(lay == pcbnew.B_SilkS)
            board.Add(t)
    add_silk(board)
    apply_edits(board)
    print('pruned after edits:', prune_dangling(board))

    # GND pours on both layers (outline from v5)
    for z in old.Zones():
        nz = pcbnew.ZONE(board)
        nz.SetLayer(z.GetLayer())
        nz.SetNet(board.FindNet('GND'))
        nz.Outline().AddOutline(z.Outline().COutline(0))
        nz.SetLocalClearance(mm(0.3))
        nz.SetMinThickness(mm(0.2))
        nz.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        nz.SetThermalReliefGap(mm(0.4))
        nz.SetThermalReliefSpokeWidth(mm(0.5))
        nz.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        board.Add(nz)
    # MOSFET sources: solid connection to the pour (they carry the load current)
    for q in ('Q1', 'Q2', 'Q3', 'Q4'):
        for pad in board.FindFootprintByReference(q).Pads():
            if pad.GetNetname() == 'GND':
                pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
    for r in ('LED1', 'LED2', 'LED3', 'LED4', 'LED5'):
        for pad in board.FindFootprintByReference(r).Pads():
            if pad.GetNetname() == 'GND':
                pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
    for pad in board.FindFootprintByReference('TVS5').Pads():
        if pad.GetNetname() == 'GND':
            pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
    for pad in board.FindFootprintByReference('J5').Pads():
        if pad.GetNetname() == 'GND':
            pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)

    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.BuildConnectivity()
    pcbnew.SaveBoard(PCB, board)
    print('saved', PCB)


# --------------------------------------------------------------------------
# v6 copper edits on top of the v5 routing
def power_edits(board):
    """v6 power-input rework (see docs/REVIEW.md), done before dangling-track
    cleanup: J5.1 (+24V_IN) -> F1 -> +24V clamp rail (+TVS5); J5.3 is GND"""
    j5 = board.FindFootprintByReference('J5')
    for pad in j5.Pads():
        for t in list(board.GetTracks()):
            if t.GetClass() == 'PCB_VIA' or t.GetNetCode() == pad.GetNetCode():
                continue
            if pad.HitTest(t.GetStart(), 0) or pad.HitTest(t.GetEnd(), 0):
                print('  removed %s track touching J5.%s' % (t.GetNetname(), pad.GetNumber()))
                board.Remove(t)

    # v5 stitching vias that collide with the new J5 pin 4 hole
    for pad in j5.Pads():
        for v in list(board.GetTracks()):
            if v.GetClass() == 'PCB_VIA' and v.GetNetname() == 'GND' and \
                    (v.GetPosition() - pad.GetPosition()).EuclideanNorm() < pad.GetSize(pcbnew.F_Cu).x / 2 + mm(0.8):
                print('  removed GND via at (%.2f, %.2f) next to J5.%s' % (v.GetPosition().x / MM, v.GetPosition().y / MM, pad.GetNumber()))
                board.Remove(v)

    def pads(ref):
        return {p.GetNumber(): (p.GetPosition().x / MM, p.GetPosition().y / MM)
                for p in board.FindFootprintByReference(ref).Pads()}
    j, f1, tv = pads('J5'), pads('F1'), pads('TVS5')
    jin = j[[str(k) for k, v in design.PARTS['J5']['nets'].items() if v == '+24V_IN'][0]]
    # +24V_IN: J5 (+24V pin) -> bottom -> via -> F1 pad 2
    add_track(board, '+24V_IN', pcbnew.B_Cu, [jin, (jin[0], 117.6), (126.6, 117.6)], 1.0)
    add_via(board, '+24V_IN', 126.6, 117.6, 0.9, 0.45)
    add_track(board, '+24V_IN', pcbnew.F_Cu, [(126.6, 117.6), (f1['2'][0], 117.6 + (f1['2'][0] - 126.6)), f1['2']], 1.0)
    # +24V: F1 pad 1 -> start of the v5 clamp rail (to DZ1/DZ2) at (134.29, 120.69)
    rail = (134.29, 120.69)
    add_track(board, '+24V', pcbnew.F_Cu, [f1['1'], (rail[0] - 0.39, f1['1'][1]), rail], 1.0)
    add_via(board, '+24V', rail[0], rail[1], 0.9, 0.45)
    # bottom: rail -> left clamp network (DZ3/DZ4) at (118.59, 104.99), TVS5 cathode on the way
    v2 = (120.0, 123.0)
    add_track(board, '+24V', pcbnew.B_Cu, [rail, (rail[0], 123.0), v2], 1.0)
    add_via(board, '+24V', v2[0], v2[1], 0.9, 0.45)
    add_track(board, '+24V', pcbnew.F_Cu, [v2, (tv['1'][0], v2[1] - (v2[0] - tv['1'][0])), tv['1']], 1.0)
    add_track(board, '+24V', pcbnew.B_Cu, [v2, (118.59, v2[1] - (v2[0] - 118.59)), (118.59, 104.99)], 1.0)


def apply_edits(board):
    # (b) GND stitching vias next to every MOSFET source group, so the load
    #     current returns through both pours now that the shunts are gone
    for q in ('Q1', 'Q2', 'Q3', 'Q4'):
        f = board.FindFootprintByReference(q)
        src = [p.GetPosition() for p in f.Pads() if p.GetNetname() == 'GND']
        placed = place_vias_near(board, src, n=4, dia=0.8, drill=0.4)
        print('  %s source vias: %s' % (q, ', '.join('(%.2f, %.2f)' % v for v in placed)))

    # (c) 78M12 tab: solid connection to the GND pour + heat-spreading vias to
    #     the bottom pour (the regulator can dissipate ~1-1.5 W, see REVIEW.md)
    u3 = board.FindFootprintByReference('U3')
    tab = [p for p in u3.Pads() if p.GetNetname() == 'GND'][0]
    tab.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
    placed = place_vias_near(board, [tab.GetPosition()], n=8, dia=0.8, drill=0.4, radius=6.0, pitch=1.4)
    print('  U3 tab vias: %s' % ', '.join('(%.2f, %.2f)' % v for v in placed))

    # (d) layer change on the D8 output path: one 0.4 mm via -> two in parallel
    out8 = D2S['OUT_D8']
    for v in [t for t in board.GetTracks() if t.GetClass() == 'PCB_VIA' and t.GetNetname() == out8]:
        add_parallel_via(board, 'OUT_D8', (v.GetPosition().x / MM, v.GetPosition().y / MM))


def add_parallel_via(board, net, near, dia=0.9, drill=0.4, radius=3.5, gap=0.2):
    """second via next to an existing one, joined on both layers by 1 mm tracks"""
    nc = board.FindNet(D2S.get(net, net)).GetNetCode()
    x0, y0 = near
    tw = 1.0
    best = None
    for i in range(-int(radius / 0.1), int(radius / 0.1) + 1):
        for j in range(-int(radius / 0.1), int(radius / 0.1) + 1):
            x, y = x0 + i * 0.1, y0 + j * 0.1
            dd = math.hypot(x - x0, y - y0)
            if dd < dia + 0.1 or dd > radius:
                continue
            ok = True
            seg_pts = [P(x0 + (x - x0) * k / 10, y0 + (y - y0) * k / 10) for k in range(11)]
            for t in board.GetTracks():
                if t.GetNetCode() == nc:
                    continue
                for q in seg_pts:
                    r = dia / 2 if q == seg_pts[-1] else tw / 2
                    if t.GetClass() == 'PCB_VIA':
                        if (t.GetPosition() - q).EuclideanNorm() < t.GetWidth(pcbnew.F_Cu) / 2 + mm(r + gap):
                            ok = False
                    elif point_on_item(t, q, mm(r + gap)):
                        ok = False
                    if not ok:
                        break
                if not ok:
                    break
            if ok:
                for f in board.GetFootprints():
                    for p in f.Pads():
                        if p.GetNetCode() == nc:
                            continue
                        for q in seg_pts:
                            r = dia / 2 if q == seg_pts[-1] else tw / 2
                            if p.HitTest(q, mm(r + gap + 0.05)):
                                ok = False
                                break
                        if not ok:
                            break
                    if not ok:
                        break
            if ok and (best is None or dd < best[0]):
                best = (dd, x, y)
    if best is None:
        print('  no room for a parallel %s via' % net)
        return None
    _, x, y = best
    for v in list(board.GetTracks()):   # stitching vias in the way go
        if v.GetClass() == 'PCB_VIA' and v.GetNetname() == 'GND' and (v.GetPosition() - P(x, y)).EuclideanNorm() < mm(dia + 0.3):
            board.Remove(v)
    add_via(board, net, x, y, dia, drill)
    add_track(board, net, pcbnew.F_Cu, [(x0, y0), (x, y)], tw)
    add_track(board, net, pcbnew.B_Cu, [(x0, y0), (x, y)], tw)
    print('  parallel %s via at (%.2f, %.2f)' % (net, x, y))
    return x, y


def place_vias_near(board, targets, n, dia, drill, radius=3.5, gap=0.35, pitch=1.3):
    """put n GND vias as close as possible to the target points, keeping
    `gap` clearance to every non-GND copper item and to other vias."""
    gnd = board.FindNet('GND').GetNetCode()
    obst = []   # (shape, clearance) of non-GND copper on either layer
    for t in board.GetTracks():
        if t.GetNetCode() != gnd:
            obst.append(t)
    pads = [p for f in board.GetFootprints() for p in f.Pads()]
    edge = board.GetBoardEdgesBoundingBox()
    cands = []
    step = 0.25
    for tp in targets:
        tx, ty = tp.x / MM, tp.y / MM
        k = int(radius / step)
        for i in range(-k, k + 1):
            for j in range(-k, k + 1):
                x, y = tx + i * step, ty + j * step
                d = math.hypot(x - tx, y - ty)
                if d <= radius:
                    cands.append((d, x, y))
    cands.sort()
    placed = []
    r = dia / 2
    for d, x, y in cands:
        if len(placed) >= n:
            break
        pt = P(x, y)
        if not edge.Contains(pt) or min(x - edge.GetX() / MM, edge.GetRight() / MM - x,
                                        y - edge.GetY() / MM, edge.GetBottom() / MM - y) < 1.0:
            continue
        if any(math.hypot(x - a, y - b) < pitch for a, b in placed):
            continue
        ok = True
        for t in obst:
            if t.GetClass() == 'PCB_VIA':
                if (t.GetPosition() - pt).EuclideanNorm() < t.GetWidth(pcbnew.F_Cu) / 2 + mm(r + gap):
                    ok = False
                    break
            elif point_on_item(t, pt, mm(r + gap)):
                ok = False
                break
        if not ok:
            continue
        for p in pads:
            # any pad (also GND SMD pads: a via in an SMD pad wicks solder)
            if p.HitTest(pt, mm(r + gap)) or (p.GetDrillSize().x and (p.GetPosition() - pt).EuclideanNorm() < p.GetDrillSize().x / 2 + mm(r + 0.5)):
                ok = False
                break
        if not ok:
            continue
        for t in board.GetTracks():
            if t.GetClass() == 'PCB_VIA' and (t.GetPosition() - pt).EuclideanNorm() < t.GetWidth(pcbnew.F_Cu) / 2 + mm(r + 0.3):
                ok = False
                break
        if not ok:
            continue
        add_via(board, 'GND', x, y, dia, drill)
        placed.append((x, y))
    return placed


# footprint changed vs v5: (pad that must sit on the v5 pad of the same number, angle)
PAD_ANCHOR = {'J5': ('1', 180, 0.3)}   # 4P body is wider: 0.3 mm right clears Q3/TVS3 and J8

# parts that did not exist in v5: (x, y, angle)
NEW_PLACEMENT = {
    'F1': (130.0, 120.3, 180),
    'TVS5': (121.8, 120.3, 0),
}

# v5 top-silk labels that sat under the terminal-block bodies: (x, y, height)
SILK_MOVE = {
    '11': (None, 82.5, 1.3), '10': (None, 82.5, 1.3), '9': (None, 82.5, 1.3), '8': (None, 82.5, 1.3),
    '5': (None, 82.5, 1.3), '4': (None, 82.5, 1.3), '3': (None, 82.5, 1.3), '2': (None, 82.5, 1.3),
    'output': (128.4, 89.6, 1.5), 'input': (151.3, 92.0, 1.5),
}


def add_silk(board):
    j5 = {p.GetNumber(): p.GetPosition() for p in board.FindFootprintByReference('J5').Pads()}
    for num, txt in [(str(k), '+24V' if v == '+24V_IN' else v) for k, v in design.PARTS['J5']['nets'].items()]:
        t = pcbnew.PCB_TEXT(board)
        t.SetText(txt)
        t.SetLayer(pcbnew.F_SilkS)
        t.SetPosition(pcbnew.VECTOR2I(j5[num].x, mm(117.5)))
        t.SetTextSize(pcbnew.VECTOR2I(mm(0.8), mm(0.8)))
        t.SetTextThickness(mm(0.15))
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
        t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
        board.Add(t)


if __name__ == '__main__':
    main()
