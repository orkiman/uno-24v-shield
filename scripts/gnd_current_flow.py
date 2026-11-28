"""Estimate how the load return current flows through the GND copper.

The filled GND pours (both layers), GND tracks, GND pads and vias are
rasterised to a 2-layer resistor grid (1 oz copper); the MOSFET source pads
inject the load currents, the J5 GND terminals are the sink.  Reports the
voltage drop per MOSFET, the worst current density (A per mm of copper width)
and writes a heat map, docs/reports/gnd_current_<scenario>.png.

Needs numpy + scipy (pip install scipy)."""
import math
import os
import sys

import numpy as np
import pcbnew
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PCB = os.path.join(ROOT, 'hardware', 'uno-24v-shield.kicad_pcb')
H = 0.15                              # grid step, mm
RS = 1.72e-8 / 35e-6                  # 1 oz copper sheet resistance, ohm/square
R_VIA_PER_MM_DRILL = 1.72e-8 * 1.6e-3 / (math.pi * 1e-3 * 20e-6)   # barrel, 20 um plating, per mm of drill dia


def raster(board, bb, layer, gnd):
    W = int(bb.GetWidth() / 1e6 / H) + 1
    Hh = int(bb.GetHeight() / 1e6 / H) + 1
    img = Image.new('1', (W, Hh), 0)
    d = ImageDraw.Draw(img)
    x0, y0 = bb.GetX() / 1e6, bb.GetY() / 1e6

    def P(v):
        return ((v.x / 1e6 - x0) / H, (v.y / 1e6 - y0) / H)
    for z in board.Zones():
        if z.GetNetCode() != gnd or not z.IsOnLayer(layer):
            continue
        polys = z.GetFilledPolysList(layer)
        for i in range(polys.OutlineCount()):
            ch = polys.COutline(i)
            d.polygon([P(ch.CPoint(k)) for k in range(ch.PointCount())], fill=1)
            for j in range(polys.HoleCount(i)):
                hh = polys.CHole(i, j)
                d.polygon([P(hh.CPoint(k)) for k in range(hh.PointCount())], fill=0)
    for t in board.GetTracks():
        if t.GetNetCode() == gnd and t.GetClass() == 'PCB_TRACK' and t.GetLayer() == layer:
            d.line([P(t.GetStart()), P(t.GetEnd())], fill=1, width=max(1, int(round(t.GetWidth() / 1e6 / H))))
    for f in board.GetFootprints():
        for p in f.Pads():
            if p.GetNetCode() == gnd and p.IsOnLayer(layer):
                b2 = p.GetBoundingBox()
                d.rectangle([P(b2.GetOrigin()), P(b2.GetEnd())], fill=1)
    return np.array(img, dtype=bool), (x0, y0)


def solve(sources, title):
    board = pcbnew.LoadBoard(PCB)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    gnd = board.FindNet('GND').GetNetCode()
    bb = board.GetBoardEdgesBoundingBox()
    top, (x0, y0) = raster(board, bb, pcbnew.F_Cu, gnd)
    bot, _ = raster(board, bb, pcbnew.B_Cu, gnd)
    ny, nx = top.shape
    cells = np.stack([top, bot])
    idx = -np.ones(cells.shape, dtype=np.int64)
    idx[cells] = np.arange(cells.sum())
    n = int(cells.sum())
    rows, cols, vals = [], [], []

    def link(a, b, g):
        rows.extend([a, b, a, b])
        cols.extend([a, b, b, a])
        vals.extend([g, g, -g, -g])
    g = 1.0 / RS
    for L in (0, 1):
        m = cells[L]
        a = idx[L][:, :-1][m[:, :-1] & m[:, 1:]]
        b_ = idx[L][:, 1:][m[:, :-1] & m[:, 1:]]
        for u, v in zip(a, b_):
            link(u, v, g)
        a = idx[L][:-1, :][m[:-1, :] & m[1:, :]]
        b_ = idx[L][1:, :][m[:-1, :] & m[1:, :]]
        for u, v in zip(a, b_):
            link(u, v, g)

    def cell(pt):
        return int(round((pt.y / 1e6 - y0) / H)), int(round((pt.x / 1e6 - x0) / H))
    nvia = 0
    for t in board.GetTracks():
        if t.GetClass() == 'PCB_VIA' and t.GetNetCode() == gnd:
            r, c = cell(t.GetPosition())
            if idx[0, r, c] >= 0 and idx[1, r, c] >= 0:
                link(idx[0, r, c], idx[1, r, c], 1.0 / (R_VIA_PER_MM_DRILL / (t.GetDrillValue() / 1e6)))
                nvia += 1
    # THT GND pads connect both layers; J5 GND pads are the sink (V = 0)
    sink = set()
    for f in board.GetFootprints():
        for p in f.Pads():
            if p.GetNetCode() != gnd or p.GetAttribute() != pcbnew.PAD_ATTRIB_PTH:
                continue
            b2 = p.GetBoundingBox()
            r0, c0 = cell(b2.GetOrigin())
            r1, c1 = cell(b2.GetEnd())
            pc = [(r, c) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)
                  if 0 <= r < ny and 0 <= c < nx and idx[0, r, c] >= 0 and idx[1, r, c] >= 0]
            for r, c in pc:
                link(idx[0, r, c], idx[1, r, c], 1e3)
                if f.GetReference() == 'J5':
                    sink.add(idx[0, r, c])
                    sink.add(idx[1, r, c])
    A = sp.csr_matrix((vals, (rows, cols)), shape=(n, n))
    I = np.zeros(n)
    src_cells = {}
    for ref, amps in sources.items():
        f = board.FindFootprintByReference(ref)
        cs = []
        for p in f.Pads():
            if p.GetNetCode() == gnd:
                b2 = p.GetBoundingBox()
                r0, c0 = cell(b2.GetOrigin())
                r1, c1 = cell(b2.GetEnd())
                cs += [idx[0, r, c] for r in range(r0, r1 + 1) for c in range(c0, c1 + 1) if idx[0, r, c] >= 0]
        I[cs] += amps / len(cs)
        src_cells[ref] = cs
    keep = np.array([i for i in range(n) if i not in sink])
    V = np.zeros(n)
    V[keep] = spla.spsolve(A[keep][:, keep].tocsc(), I[keep])
    # current density (A per mm of width) at each cell
    Vg = np.full(cells.shape, np.nan)
    Vg[cells] = V
    J = np.zeros(cells.shape)
    for L in (0, 1):
        gx = np.zeros((ny, nx))
        gy = np.zeros((ny, nx))
        dx = np.diff(Vg[L], axis=1) / RS / H
        dy = np.diff(Vg[L], axis=0) / RS / H
        gx[:, :-1] = np.nan_to_num(dx)
        gy[:-1, :] = np.nan_to_num(dy)
        J[L] = np.hypot(gx, gy)
    res = {'title': title, 'vias': nvia}
    res['drop_mV'] = {ref: 1e3 * V[cs].mean() for ref, cs in src_cells.items()}
    # ignore the cells right at sources / sink (current enters there)
    mask = np.ones(cells.shape, bool)
    for ref in sources:
        f = board.FindFootprintByReference(ref)
        b2 = f.GetBoundingBox(False)
        r0, c0 = cell(b2.GetOrigin())
        r1, c1 = cell(b2.GetEnd())
        mask[:, max(r0 - 3, 0):r1 + 4, max(c0 - 3, 0):c1 + 4] = False
    f = board.FindFootprintByReference('J5')
    b2 = f.GetBoundingBox(False)
    r0, c0 = cell(b2.GetOrigin())
    r1, c1 = cell(b2.GetEnd())
    mask[:, max(r0 - 3, 0):r1 + 4, max(c0 - 3, 0):c1 + 4] = False
    Jm = np.where(mask & cells, J, 0)
    L, r, c = np.unravel_index(np.argmax(Jm), Jm.shape)
    res['max_J'] = (float(Jm[L, r, c]), 'top' if L == 0 else 'bottom', round(x0 + c * H, 1), round(y0 + r * H, 1))
    res['p99_J'] = float(np.percentile(Jm[Jm > 0.05], 99)) if (Jm > 0.05).any() else 0.0
    res['power_mW'] = 1e3 * float(V @ I)
    # heat map
    img = np.zeros((ny, nx, 3), np.uint8)
    img[top | bot] = (40, 40, 40)
    Jc = np.maximum(J[0], J[1])
    norm = np.clip(Jc / 3.0, 0, 1)
    col = (np.stack([norm, 1 - np.abs(norm - 0.5) * 2, 1 - norm], -1) * 255).astype(np.uint8)
    on = (top | bot) & (Jc > 0.05)
    img[on] = col[on]
    out = Image.fromarray(img).resize((nx * 3, ny * 3), Image.NEAREST)
    d = ImageDraw.Draw(out)
    d.text((10, 10), '%s   blue = low, green = 1.5 A/mm, red >= 3 A/mm' % title, fill=(255, 255, 255))
    fn = os.path.join(ROOT, 'docs', 'reports', 'gnd_current_%s.png' % title.split()[0])
    out.save(fn)
    res['image'] = fn
    return res


SCENARIOS = {
    'even 4 x 1.25 A': {'Q1': 1.25, 'Q2': 1.25, 'Q3': 1.25, 'Q4': 1.25},
    'far 2+2+1 A (Q1,Q2 far side)': {'Q1': 2.0, 'Q2': 2.0, 'Q4': 1.0},
}

if __name__ == '__main__':
    for name, src in SCENARIOS.items():
        r = solve(src, name)
        print('== %s' % name)
        print('   drop to J5 (mV):', {k: round(v, 1) for k, v in r['drop_mV'].items()})
        print('   max current density %.2f A/mm on %s at (%.1f, %.1f); 99th pct %.2f A/mm' % (
            r['max_J'][0], r['max_J'][1], r['max_J'][2], r['max_J'][3], r['p99_J']))
        print('   copper loss in GND: %.0f mW, vias modelled: %d, map: %s' % (r['power_mW'], r['vias'], r['image']))
    sys.exit(0)
