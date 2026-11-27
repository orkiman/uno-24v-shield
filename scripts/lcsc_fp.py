"""LCSC / JLCPCB library data (cached in source/lcsc/*.json):

* convert an LCSC (EasyEDA std) footprint to a KiCad .kicad_mod, so the
  footprint on our board is exactly the one JLCPCB places the part with
* check_parts(): for every BOM line compare our footprint with JLCPCB's and
  check that the pin JLCPCB calls cathode / pin 1 carries the intended net.
"""
import json
import os
import re

import sexp

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(os.path.dirname(HERE), 'source', 'lcsc')
U = 0.254  # EasyEDA std unit (10 mil) in mm


def load(code):
    with open(os.path.join(CACHE, code + '.json'), encoding='utf-8') as f:
        return json.load(f)


def _path_points(d):
    nums = [float(v) for v in re.findall(r'-?\d+\.?\d*', d.split('A')[0])]
    return list(zip(nums[0::2], nums[1::2]))


def parse(code):
    """-> dict(title, pads={num: dict(x,y,w,h,shape,drill)}, silk=[lines], marks=[polys], crtyd=bbox)
    coordinates in mm relative to the footprint origin, y down"""
    d = load(code)['package']
    ox, oy = float(d['head']['x']), float(d['head']['y'])
    pads, silk, marks, crt = {}, [], [], []
    for s in d['shape']:
        f = s.split('~')
        if f[0] == 'PAD':
            hole = float(f[9]) * 2 * U if f[9] not in ('', '0') else 0.0
            pads[f[8]] = dict(shape=f[1], x=(float(f[2]) - ox) * U, y=(float(f[3]) - oy) * U,
                              w=float(f[4]) * U, h=float(f[5]) * U, drill=hole, layer=f[6],
                              rot=float(f[11]) if len(f) > 11 and f[11] not in ('',) else 0.0)
        elif f[0] == 'TRACK' and f[2] == '3':
            pts = [float(v) for v in f[4].split()]
            xy = [((pts[i] - ox) * U, (pts[i + 1] - oy) * U) for i in range(0, len(pts), 2)]
            silk.append((float(f[1]) * U, xy))
        elif f[0] == 'SOLIDREGION' and f[1] == '3':
            marks.append([((x - ox) * U, (y - oy) * U) for x, y in _path_points(f[3])])
        elif f[0] == 'SOLIDREGION' and f[1] == '99':
            crt += [((x - ox) * U, (y - oy) * U) for x, y in _path_points(f[3])]
    return dict(title=d['title'], pads=pads, silk=silk, marks=marks, crtyd=crt)


def kicad_mod(code, name=None):
    p = parse(code)
    name = name or p['title']
    tht = any(v['drill'] for v in p['pads'].values())
    out = ['footprint', name, ['version', 20241229], ['generator', 'uno24v_scripts'], ['layer', 'F.Cu'],
           ['descr', 'LCSC/JLCPCB footprint %s (from %s)' % (p['title'], code)],
           ['attr', sexp.Sym('through_hole' if tht else 'smd')],
           ['property', 'Reference', 'REF**', ['at', 0, -3, 0], ['layer', 'F.Fab'],
            ['effects', ['font', ['size', 0.6, 0.6], ['thickness', 0.1]]]],
           ['property', 'Value', name, ['at', 0, 3, 0], ['layer', 'F.Fab'], ['hide', sexp.Sym('yes')],
            ['effects', ['font', ['size', 0.6, 0.6], ['thickness', 0.1]]]]]
    for w, xy in p['silk']:
        for (x1, y1), (x2, y2) in zip(xy, xy[1:]):
            out.append(['fp_line', ['start', round(x1, 4), round(y1, 4)], ['end', round(x2, 4), round(y2, 4)],
                        ['stroke', ['width', max(round(w, 3), 0.12)], ['type', sexp.Sym('solid')]],
                        ['layer', 'F.SilkS']])
    for poly in p['marks']:
        out.append(['fp_poly', ['pts'] + [['xy', round(x, 4), round(y, 4)] for x, y in poly],
                    ['stroke', ['width', 0], ['type', sexp.Sym('solid')]], ['fill', sexp.Sym('yes')],
                    ['layer', 'F.SilkS']])
    if p['crtyd']:
        xs = [x for x, y in p['crtyd']]
        ys = [y for x, y in p['crtyd']]
        out.append(['fp_rect', ['start', round(min(xs) - 0.1, 3), round(min(ys) - 0.1, 3)],
                    ['end', round(max(xs) + 0.1, 3), round(max(ys) + 0.1, 3)],
                    ['stroke', ['width', 0.05], ['type', sexp.Sym('solid')]], ['fill', sexp.Sym('no')],
                    ['layer', 'F.CrtYd']])
    for num, v in sorted(p['pads'].items(), key=lambda kv: kv[0]):
        if v['drill']:
            shp = 'rect' if v['shape'] == 'RECT' else 'circle' if abs(v['w'] - v['h']) < 1e-3 else 'oval'
            out.append(['pad', num, sexp.Sym('thru_hole'), sexp.Sym(shp), ['at', round(v['x'], 4), round(v['y'], 4)],
                        ['size', round(v['w'], 4), round(v['h'], 4)], ['drill', round(v['drill'], 4)],
                        ['layers', '*.Cu', '*.Mask']])
        else:
            shp = 'rect' if v['shape'] == 'RECT' else 'oval'
            out.append(['pad', num, sexp.Sym('smd'), sexp.Sym(shp), ['at', round(v['x'], 4), round(v['y'], 4)],
                        ['size', round(v['w'], 4), round(v['h'], 4)], ['layers', 'F.Cu', 'F.Paste', 'F.Mask']])
    out.append(['embedded_fonts', sexp.Sym('no')])
    return sexp.dump(out) + '\n'


# ---------------------------------------------------------------- checks
def _our_pads(fp_file):
    t = sexp.parse(open(fp_file, encoding='utf-8').read())
    pads = {}
    for p in sexp.find(t, 'pad'):
        at = sexp.find1(p, 'at')
        pads[str(p[1])] = (float(at[1]), float(at[2]))
    return pads


def _centred(pads):
    cx = sum(v[0] for v in pads.values()) / len(pads)
    cy = sum(v[1] for v in pads.values()) / len(pads)
    return {k: (v[0] - cx, v[1] - cy) for k, v in pads.items()}


CATHODE_NAMES = ('K', 'C', '-')


def check_parts(parts, fplib):
    """returns list of (ref-list, lcsc, result, detail)"""
    rows = []
    groups = {}
    for ref, p in parts.items():
        groups.setdefault((p['lcsc'], p['fp']), []).append(ref)
    for (code, fp), refs in sorted(groups.items(), key=lambda kv: kv[1][0]):
        lc = load(code)
        jl = _centred({k: (v['x'], v['y']) for k, v in parse(code)['pads'].items()})
        ours = _centred(_our_pads(os.path.join(fplib, fp + '.kicad_mod')))
        same = set(jl) == set(ours) and all(abs(ours[k][0] - jl[k][0]) < 0.3 and abs(ours[k][1] - jl[k][1]) < 0.3
                                            for k in jl)
        res = 'footprint = JLCPCB' if same else 'FOOTPRINT DIFFERS'
        detail = ''
        if not same and len(jl) == len(ours):
            # same hole pattern with different pin numbers?
            js = sorted((round(x, 1), round(y, 1)) for x, y in jl.values())
            os_ = sorted((round(x, 1), round(y, 1)) for x, y in ours.values())
            if all(abs(a[0] - b[0]) < 0.3 and abs(a[1] - b[1]) < 0.3 for a, b in zip(js, os_)):
                res = 'same pads, numbering'
                detail = ('identical pad pattern; JLC library numbers the pins mirrored - the part fits one way '
                          'only, so the physical part defines the wiring (see REVIEW.md)')
        p0 = parts[refs[0]]
        if p0.get('cathode'):
            kpins = [n for n, nm in lc['pins'].items() if nm in CATHODE_NAMES]
            bad = []
            for r in refs:
                want = parts[r]['cathode']
                got = [parts[r]['nets'].get(int(n)) for n in kpins]
                if got != [want]:
                    bad.append('%s cathode pin %s carries %s, expected %s' % (r, kpins, got, want))
            # JLC silkscreen polarity cue must be on the cathode pad:
            #  - a solid band clearly on one side (diodes), or
            #  - the chamfered end of the outline (LEDs)
            pp = parse(code)
            xs = {n: v['x'] for n, v in pp['pads'].items()}
            half = max(abs(v) for v in xs.values())
            cues = []
            for poly in pp['marks']:
                mx = sum(x for x, y in poly) / len(poly)
                if abs(mx) > 0.35 * half:
                    cues.append(('band', mx))
            segs = [((x1, y1), (x2, y2)) for w, xy in pp['silk'] for (x1, y1), (x2, y2) in zip(xy, xy[1:])
                    if abs(x2 - x1) > 1e-3 and abs(y2 - y1) > 1e-3]
            centre = [s_ for s_ in segs if abs((s_[0][0] + s_[1][0]) / 2) < 0.5 * half]
            outer = [s_ for s_ in segs if abs((s_[0][0] + s_[1][0]) / 2) >= 0.5 * half]
            if len(centre) >= 2:
                # diode glyph: the triangle apex (end shared by two slanted lines) points at the cathode
                ends = {}
                for a, b_ in centre:
                    for e in (a, b_):
                        k = (round(e[0], 1), round(e[1], 1))
                        ends[k] = ends.get(k, 0) + 1
                apex = [k for k, n in ends.items() if n >= 2]
                if apex:
                    cues.append(('diode glyph', apex[0][0]))
            if outer and not cues:
                cues.append(('chamfer', sum((a[0] + b_[0]) / 2 for a, b_ in outer) / len(outer)))
            evidence = []
            for kind, mx in cues:
                side = min(xs, key=lambda n: abs(xs[n] - mx))
                evidence.append('%s at pad %s' % (kind, side))
                if side != kpins[0]:
                    bad.append('JLC silk %s is at pad %s, symbol says cathode = pad %s' % (kind, side, kpins[0]))
            detail = '; '.join(bad) if bad else 'cathode = pin %s (%s), JLC silk: %s -> OK' % (
                kpins[0], lc['pins'][kpins[0]], ', '.join(evidence) or 'no polarity cue')
            if bad:
                res = 'POLARITY PROBLEM'
        rows.append((refs, code, fp, res, detail))
    return rows
