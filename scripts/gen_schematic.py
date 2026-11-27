"""Generate the KiCad schematic (hardware/*.kicad_sch) from design.py.

Layout: a root overview page plus one page per functional block.  Inside a
block everything is connected with real wires; only signals that travel
between pages use global labels (D2..D11, D0_RX, D1_TX, ARD_VIN) and the
power nets use power symbols.

The drawing is checked three ways: every pin must land on a wire end, label,
power pin or no-connect flag (checked here), the exported netlist must equal
design.py (checked in build_pcb.py) and ERC must be clean."""
import math
import os
import uuid as _uuid

import design
import kicadlib
import sexp
from sexp import Sym

PROJECT = 'uno-24v-shield'
HW = kicadlib.PROJ
NS = _uuid.UUID('6f1c2a52-6d1e-4a7e-9b1f-2d0c5e1a7b00')
G = 2.54


def uid(*key):
    return str(_uuid.uuid5(NS, '/'.join(str(k) for k in key)))


ROOT = uid('root')


def snap(v):
    return round(round(v / 1.27) * 1.27, 4)


def P(x, y):
    return (snap(x), snap(y))


def xf(px, py, rot, mirror=False):
    """library point -> screen offset (y down); rot CCW in degrees"""
    r = math.radians(rot)
    x = px * math.cos(r) - py * math.sin(r)
    y = px * math.sin(r) + py * math.cos(r)
    x, y = round(x, 4), round(-y, 4)
    return (-x, y) if mirror else (x, y)


def outward(angle, rot, mirror=False):
    a = math.radians(angle + 180 + rot)
    dx, dy = round(math.cos(a)), round(-math.sin(a))
    return (-dx, dy) if mirror else (dx, dy)


def font(size=1.27, bold=False, justify=None, hide=False):
    e = ['effects', ['font', ['size', size, size]] + ([['bold', Sym('yes')]] if bold else [])]
    if justify:
        e.append(['justify'] + [Sym(j) for j in justify.split()])
    if hide:
        e.append(['hide', Sym('yes')])
    return e


def prop(key, val, x, y, ang=0, hide=False, justify=None, size=1.27):
    return ['property', key, val, ['at', round(x, 3), round(y, 3), ang], font(size, hide=hide, justify=justify)]


def unit_pins(sym, unit):
    """pins that belong to `unit` (or to all units)"""
    out = []
    for u in sexp.find(sym, 'symbol'):
        parts = u[1].rsplit('_', 2)
        un = int(parts[-2])
        if un in (0, unit):
            out += kicadlib.pins(['x', u])
    return out


PWR_COUNTER = [0]


class Inst:
    def __init__(self, page, ref, x, y, rot, mirror, unit):
        self.page, self.ref, self.x, self.y, self.rot, self.mirror, self.unit = page, ref, x, y, rot, mirror, unit
        self.part = design.PARTS[ref]
        self.sym = kicadlib.get_symbol(self.part['sym'])
        self.pins = unit_pins(self.sym, unit)

    def pin(self, num):
        num = str(num)
        q = [p for p in self.pins if p['number'] == num]
        assert q, (self.ref, num, [p['number'] for p in self.pins])
        q = q[0]
        ox, oy = xf(q['x'], q['y'], self.rot, self.mirror)
        return P(self.x + ox, self.y + oy)

    def pin_dir(self, num):
        q = [p for p in self.pins if p['number'] == str(num)][0]
        return outward(q['angle'], self.rot, self.mirror)


class Page:
    def __init__(self, name, fname, paper, title, page_no):
        self.name, self.fname, self.paper, self.title, self.page_no = name, fname, paper, title, page_no
        self.sheet_uuid = uid('sheet', name) if name else ROOT
        self.file_uuid = uid('file', fname)
        self.items = []
        self.lib_ids = set()
        self.insts = []
        self.points = {}      # connection point -> count (for junctions)
        self.wires = []
        self.nc_pts = set()
        self.label_pts = set()

    # ---------------------------------------------------------------- paths
    @property
    def inst_path(self):
        return '/' + ROOT if not self.name else '/' + ROOT + '/' + self.sheet_uuid

    # ---------------------------------------------------------------- items
    def _pt(self, p):
        self.points[p] = self.points.get(p, 0) + 1

    def wire(self, *pts):
        pts = [P(*p) for p in pts]
        for a, b in zip(pts, pts[1:]):
            if a == b:
                continue
            assert a[0] == b[0] or a[1] == b[1], ('non-orthogonal wire', a, b)
            self.wires.append((a, b))
            self._pt(a)
            self._pt(b)

    def label(self, net, p, d=(1, 0), glob=False, shape='bidirectional'):
        p = P(*p)
        ang = {(1, 0): 0, (-1, 0): 180, (0, -1): 90, (0, 1): 270}[d]
        just = 'left bottom' if ang in (0, 90) else 'right bottom'
        self.label_pts.add(p)
        self._pt(p)
        if glob:
            just = 'left' if ang in (0, 90) else 'right'
            self.items.append(['global_label', net, ['shape', Sym(shape)], ['at', p[0], p[1], ang],
                               ['fields_autoplaced', Sym('yes')], font(justify=just), ['uuid', uid('gl', self.name, net, p)],
                               ['property', 'Intersheetrefs', '${INTERSHEET_REFS}', ['at', p[0], p[1], ang],
                                font(justify=just, hide=True)]])
        else:
            self.items.append(['label', net, ['at', p[0], p[1], ang], ['fields_autoplaced', Sym('yes')],
                               font(justify=just), ['uuid', uid('l', self.name, net, p)]])

    def glabel(self, net, p, d, shape='bidirectional'):
        self.label(net, p, d, glob=True, shape=shape)

    def nc(self, p):
        p = P(*p)
        self.nc_pts.add(p)
        self.items.append(['no_connect', ['at', p[0], p[1]], ['uuid', uid('nc', self.name, p)]])

    def text(self, s, x, y, size=1.27, bold=False):
        self.items.append(['text', s, ['exclude_from_sim', Sym('no')], ['at', x, y, 0],
                           font(size, bold=bold, justify='left bottom'), ['uuid', uid('t', self.name, s, x, y)]])

    def power(self, net, p, d=None):
        """power symbol (or PWR_FLAG) with its pin at p; body points along d"""
        lib_id = 'power:PWR_FLAG' if net == 'PWR_FLAG' else design.POWER_SYMBOL_NETS[net]
        p = P(*p)
        if d is None:
            d = (0, 1) if net == 'GND' else (0, -1)
        self.lib_ids.add(lib_id)
        PWR_COUNTER[0] += 1
        ref = ('#FLG%03d' if net == 'PWR_FLAG' else '#PWR%03d') % PWR_COUNTER[0]
        base = (0, 1) if lib_id == 'power:GND' else (0, -1)
        rot = {((0, 1), (0, 1)): 0, ((0, 1), (1, 0)): 90, ((0, 1), (0, -1)): 180, ((0, 1), (-1, 0)): 270,
               ((0, -1), (0, -1)): 0, ((0, -1), (-1, 0)): 90, ((0, -1), (0, 1)): 180, ((0, -1), (1, 0)): 270}[(base, d)]
        if d[0]:
            vx, vy, vj = p[0] + d[0] * 4.4, p[1], ('left' if d[0] > 0 else 'right')
        else:
            vx, vy, vj = p[0], p[1] + d[1] * 3.4 + (0.6 if d[1] > 0 else 0), None
        self._pt(p)
        self.items.append(['symbol', ['lib_id', lib_id], ['at', p[0], p[1], rot], ['unit', 1],
                           ['exclude_from_sim', Sym('no')], ['in_bom', Sym('yes')], ['on_board', Sym('yes')],
                           ['dnp', Sym('no')], ['uuid', uid('pwr', self.name, ref)],
                           prop('Reference', ref, p[0], p[1], hide=True),
                           prop('Value', lib_id.split(':')[1], vx, vy, rot % 180, justify=vj),
                           prop('Footprint', '', p[0], p[1], hide=True),
                           prop('Datasheet', '', p[0], p[1], hide=True),
                           prop('Description', '', p[0], p[1], hide=True),
                           ['pin', '1', ['uuid', uid('pwrpin', self.name, ref)]],
                           ['instances', ['project', PROJECT, ['path', self.inst_path, ['reference', ref], ['unit', 1]]]]])

    def place(self, ref, x, y, rot=0, mirror=False, unit=1, fields='auto'):
        x, y = snap(x), snap(y)
        ins = Inst(self, ref, x, y, rot, mirror, unit)
        p = ins.part
        lib_id = p['sym']
        self.lib_ids.add(lib_id)
        self.insts.append(ins)
        rx, ry, vx, vy, just = field_pos(ins, fields)
        fa = rot % 180
        if rot in (90, 180) and just == 'left':
            just = 'right'
        if mirror:
            just = {'left': 'right', 'right': 'left'}.get(just, just)
        hide = fields == 'hide'
        props = [prop('Reference', p['ref'], rx, ry, fa, justify=just, hide=hide),
                 prop('Value', p['value'], vx, vy, fa, justify=just, hide=hide),
                 prop('Footprint', design.FP_LIB + ':' + p['fp'], x, y, hide=True),
                 prop('Datasheet', '', x, y, hide=True),
                 prop('Description', p['desc'], x, y, hide=True),
                 prop('LCSC', p['lcsc'], x, y, hide=True),
                 prop('MPN', p['mpn'], x, y, hide=True)]
        if p['old']:
            props.append(prop('v5 ref', p['old'], x, y, hide=True))
        e = ['symbol', ['lib_id', lib_id], ['at', x, y, rot]]
        if mirror:
            e.append(['mirror', Sym('y')])
        e += [['unit', unit], ['exclude_from_sim', Sym('no')], ['in_bom', Sym('yes')], ['on_board', Sym('yes')],
              ['dnp', Sym('no')], ['uuid', sym_uuid(ref, unit)]] + props
        for q in ins.pins:
            e.append(['pin', q['number'], ['uuid', uid('pin', ref, q['number'])]])
        e.append(['instances', ['project', PROJECT, ['path', self.inst_path, ['reference', ref], ['unit', unit]]]])
        self.items.append(e)
        for q in ins.pins:
            self._pt(ins.pin(q['number']))
        return ins

    def place2(self, ref, x, y, first_net, orient='v', unit=None, second_net=None, fields='auto'):
        """2-pin part (or one resistor of a pack): rotate so that the pin on
        `first_net` is at the top ('v') or on the left ('h')."""
        p = design.PARTS[ref]
        nets = {str(k): v for k, v in p['nets'].items()}
        if unit is None:
            unit = 1
            if 'Pack04' in p['sym']:
                for u in range(1, 5):
                    pair = (nets.get(str(u)), nets.get(str(9 - u)))
                    if first_net in pair and (second_net is None or second_net in pair):
                        unit = u
                        break
        for rot in (0, 90, 180, 270):
            ins = Inst(self, ref, snap(x), snap(y), rot, False, unit)
            pts = {q['number']: ins.pin(q['number']) for q in ins.pins}
            if len(set(pts.values())) != 2:
                continue
            a = [n for n in pts if nets.get(n) == first_net]
            if not a:
                raise AssertionError((ref, first_net, nets))
            pa = pts[a[0]]
            other = [v for k, v in pts.items() if k != a[0]][0]
            if orient == 'v' and pa[0] == other[0] and pa[1] < other[1]:
                return self.place(ref, x, y, rot, unit=unit, fields=fields)
            if orient == 'h' and pa[1] == other[1] and pa[0] < other[0]:
                return self.place(ref, x, y, rot, unit=unit, fields=fields)
        raise AssertionError((ref, first_net, orient))

    # ---------------------------------------------------------------- checks
    def finish(self):
        # split wires at labels placed on them (labels sit on a wire end)
        split = []
        for a, b in self.wires:
            inner = sorted([p for p in self.label_pts if p not in (a, b) and (
                (a[0] == b[0] == p[0] and min(a[1], b[1]) < p[1] < max(a[1], b[1])) or
                (a[1] == b[1] == p[1] and min(a[0], b[0]) < p[0] < max(a[0], b[0])))],
                key=lambda p: abs(p[0] - a[0]) + abs(p[1] - a[1]))
            pts = [a] + inner + [b]
            for u, v in zip(pts, pts[1:]):
                split.append((u, v))
            for p in inner:
                self.points[p] = self.points.get(p, 0) + 2
        self.wires = split
        for a, b in self.wires:
            self.items.append(['wire', ['pts', ['xy', a[0], a[1]], ['xy', b[0], b[1]]],
                               ['stroke', ['width', 0], ['type', Sym('default')]], ['uuid', uid('w', self.name, a, b)]])
        # junctions where three or more things meet
        for p, n in self.points.items():
            if n - (1 if p in self.label_pts else 0) >= 3:
                self.items.append(['junction', ['at', p[0], p[1]], ['diameter', 0], ['color', 0, 0, 0, 0],
                                   ['uuid', uid('j', self.name, p)]])
        # every pin must be connected or flagged; no pin/label inside a wire
        ends = {}
        for a, b in self.wires:
            ends[a] = ends.get(a, 0) + 1
            ends[b] = ends.get(b, 0) + 1
        errs = []
        for ins in self.insts:
            nets = {str(k): v for k, v in ins.part['nets'].items()}
            seen = set()
            for q in ins.pins:
                pt = ins.pin(q['number'])
                if pt in seen:
                    continue
                seen.add(pt)
                stacked = [r['number'] for r in ins.pins if ins.pin(r['number']) == pt]
                has_net = any(nets.get(n) for n in stacked)
                touched = pt in ends or pt in self.label_pts or self.points.get(pt, 0) >= 2
                if has_net and not touched:
                    errs.append('%s pin %s unconnected' % (ins.ref, q['number']))
                if not has_net and pt not in self.nc_pts:
                    errs.append('%s pin %s needs no-connect' % (ins.ref, q['number']))
        for a, b in self.wires:
            for p in self.points:
                if p in (a, b):
                    continue
                if (a[0] == b[0] == p[0] and min(a[1], b[1]) < p[1] < max(a[1], b[1])) or \
                   (a[1] == b[1] == p[1] and min(a[0], b[0]) < p[0] < max(a[0], b[0])):
                    errs.append('point %s lies inside wire %s-%s' % (p, a, b))
        assert not errs, '\n'.join([self.fname] + errs)

    def write(self, extra=()):
        self.finish()
        libs = ['lib_symbols']
        for lib_id in sorted(self.lib_ids):
            s = kicadlib.get_symbol(lib_id)
            s[1] = lib_id
            libs.append(s)
        doc = ['kicad_sch', ['version', 20250114], ['generator', 'eeschema'], ['generator_version', '9.0'],
               ['uuid', self.file_uuid if self.name else ROOT], ['paper', self.paper],
               ['title_block', ['title', 'Arduino UNO 24V Shield - ' + self.title], ['date', '2026-11-26'],
                ['rev', '6.0'], ['comment', 1, 'Outputs D8-D11, inputs D2-D5, RS232 D0/D1'],
                ['comment', 2, 'Derived from EasyEDA v5 (2025-10-22)']],
               libs] + self.items + list(extra)
        if not self.name:
            doc.append(['sheet_instances', ['path', '/', ['page', '1']]])
        doc.append(['embedded_fonts', Sym('no')])
        with open(os.path.join(HW, self.fname), 'w', encoding='utf-8') as f:
            f.write(sexp.dump(doc) + '\n')


def sym_uuid(ref, unit=1):
    return uid('sym', ref) if unit == 1 else uid('sym', ref, unit)


FP_PATHS = {}


def fp_path(ref):
    """KIID path the PCB footprint must carry for schematic parity"""
    return FP_PATHS[ref]


def field_pos(ins, mode):
    pts = [ins.pin(q['number']) for q in ins.pins]
    xs = [p[0] - ins.x for p in pts]
    ys = [p[1] - ins.y for p in pts]
    sides = {ins.pin_dir(q['number']) for q in ins.pins}
    x0, y0 = ins.x, ins.y
    if mode == 'left':
        x = x0 + min(xs + [0]) - 2.0
        return x, y0 - 1.27, x, y0 + 1.27, 'right'
    if mode in ('above', 'hide'):
        return x0 - 3.0, y0 - 5.4, x0 - 3.0, y0 - 3.3, 'left'
    if (0, -1) in sides and (0, 1) in sides and (1, 0) not in sides and (-1, 0) not in sides:
        x = x0 + max(xs + [0]) + 2.0
        return x, y0 - 1.27, x, y0 + 1.27, 'left'
    if 'BSC0805LS' in ins.part['sym']:
        return x0 + 5.08, y0 - 1.27, x0 + 5.08, y0 + 1.27, 'left'
    if sides <= {(1, 0), (-1, 0)} and len(pts) == 2:
        return x0 - 2.54, y0 - 3.3, x0 - 2.54, y0 + 3.8, 'left'
    top = min(min(ys), -2.54)
    if (0, -1) in sides:
        x = x0 + max(xs) - 2.54
        return x, y0 + top + 1.27, x, y0 + top + 3.3, 'left'
    return x0 - 1.27, y0 + top - 5.3, x0 - 1.27, y0 + top - 3.2, 'left'


# ============================================================================ pages
def page_power():
    pg = Page('Power', 'power.kicad_sch', 'A4', 'Power input', 2)
    pg.text('24V INPUT: resettable fuse, TVS and reverse-polarity crowbar; 12V for Arduino VIN', 20.32, 30.48, 2.0, True)
    j5 = pg.place('J5', 33.02, 60.96, mirror=True)
    jn = design.PARTS['J5']['nets']
    pin_in = [k for k, v in jn.items() if v == '+24V_IN'][0]
    pg_gnd = sorted(k for k, v in jn.items() if v == 'GND')
    # GND pins
    gp = [j5.pin(k) for k in pg_gnd]
    for q in gp:
        pg.wire(q, (45.72, q[1]))
    pg.wire(*[(45.72, q[1]) for q in gp], (45.72, gp[-1][1] + 5.08))
    pg.power('GND', (45.72, gp[-1][1] + 5.08))
    pg.wire((45.72, gp[-1][1]), (50.8, gp[-1][1]))
    pg.power('PWR_FLAG', (50.8, gp[-1][1]))
    # +24V_IN -> F1 -> +24V
    p1 = j5.pin(pin_in)
    nodeP = (55.88, p1[1])
    pg.wire(p1, nodeP)
    pg.label('+24V_IN', (48.26, p1[1]), (0, -1))
    f1 = pg.place2('F1', 66.04, p1[1], '+24V_IN', 'h')
    pg.wire(nodeP, f1.pin(2))
    nodeQ = (83.82, p1[1])
    pg.wire(f1.pin(1), nodeQ)
    pg.wire(nodeQ, (83.82, 48.26))
    pg.power('+24V', (83.82, 48.26))
    pg.wire(nodeQ, (96.52, p1[1]))
    pg.power('PWR_FLAG', (96.52, p1[1]))
    tvs = pg.place2('TVS5', 83.82, p1[1] + 11.43, '+24V', 'v')
    pg.wire(nodeQ, tvs.pin(1))
    pg.power('GND', tvs.pin(2))
    pg.text('to flyback clamps (Outputs page)', 86.36, 47.0, 1.27)
    # D1 -> 78M12 -> ARD_VIN
    yR = 91.44
    pg.wire(nodeP, (55.88, yR))
    d1 = pg.place2('D1', 66.04, yR, '+24V_IN', 'h')
    pg.wire((55.88, yR), d1.pin(2))
    u3 = pg.place('U3', 99.06, yR)
    nodeV = (83.82, yR)
    pg.wire(d1.pin(1), nodeV, u3.pin(1))
    pg.label('VREG_IN', (76.2, yR), (0, -1))
    pg.power('PWR_FLAG', nodeV)
    pg.power('GND', u3.pin(2))
    pg.wire(u3.pin(3), (119.38, yR))
    pg.glabel('ARD_VIN', (119.38, yR), (1, 0), 'output')
    # 5V indicator
    pg.text('+5V indicator', 152.4, 40.64, 1.5, True)
    x5 = 160.02
    pg.power('+5V', (x5, 48.26))
    r1 = pg.place2('R1', x5, 55.88, '+5V', 'v')
    pg.wire((x5, 48.26), r1.pin(2))
    pg.wire((x5, 48.26), (167.64, 48.26))
    pg.power('PWR_FLAG', (167.64, 48.26))
    led = pg.place2('LED1', x5, 68.58, 'LED_5V', 'v')
    pg.wire(r1.pin(1), led.pin(1))
    pg.power('GND', led.pin(2))
    notes = [
        'F1 + TVS5: a surge on the 24V line is clamped by TVS5 (SMBJ28A, VBR 31.1 V, VC 45.4 V).',
        'If 24V and GND are swapped, TVS5 conducts and F1 trips (resets after the fault is removed).',
        'F1 carries only the board current and the flyback pulses, not the load current.',
        'J5 pins 2, 3, 4 are GND: the return current of all outputs (5 A max) is split over three terminals.',
        'D1 blocks reverse voltage to the regulator; 78M12 feeds the Arduino VIN pin (12 V).',
    ]
    for i, s in enumerate(notes):
        pg.text(s, 20.32, 125.0 + i * 4.0, 1.5)
    return pg


ARD_NAMES = {
    'J1': ['NC', 'IOREF', 'RESET', '3.3V', '5V', 'GND', 'GND', 'VIN'],
    'J4': ['A0', 'A1', 'A2', 'A3', 'A4', 'A5'],
    'J2': ['SCL', 'SDA', 'AREF', 'GND', 'D13', 'D12', 'D11', 'D10', 'D9', 'D8'],
    'J3': ['D7', 'D6', 'D5', 'D4', 'D3', 'D2', 'D1/TX', 'D0/RX'],
}
GLOBAL_NETS = ['D2', 'D3', 'D4', 'D5', 'D8', 'D9', 'D10', 'D11', 'D0_RX', 'D1_TX', 'ARD_VIN']


def page_arduino():
    pg = Page('Arduino', 'arduino.kicad_sch', 'A4', 'Arduino UNO headers', 3)
    pg.text('ARDUINO UNO HEADERS (shield plugs into the UNO)', 20.32, 30.48, 2.0, True)
    for ref, x, y in (('J1', 76.2, 55.88), ('J4', 76.2, 116.84), ('J2', 190.5, 55.88), ('J3', 190.5, 116.84)):
        j = pg.place(ref, x, y)
        nets = design.PARTS[ref]['nets']
        n = len(ARD_NAMES[ref])
        for k in range(1, n + 1):
            pt = j.pin(k)
            pg.text(ARD_NAMES[ref][k - 1], x + 3.81, pt[1] + 0.6, 1.27)
            net = nets.get(k)
            if net is None:
                pg.nc(pt)
                continue
            end = (pt[0] - 5.08, pt[1])
            pg.wire(pt, end)
            if net in design.POWER_SYMBOL_NETS:
                pg.power(net, end, (-1, 0))
            elif net in GLOBAL_NETS:
                pg.glabel(net, end, (-1, 0), 'input' if ref == 'J3' and k in (3, 4, 5, 6) else
                          'output' if ref == 'J2' else 'bidirectional')
            elif net == 'RESET':
                sw = pg.place2('SW1', pt[0] - 12.7, pt[1], 'GND', 'h', fields='above')
                pg.wire(end, sw.pin(2))
                pg.wire(sw.pin(1), (sw.pin(1)[0] - 2.54, pt[1]))
                pg.power('GND', (sw.pin(1)[0] - 2.54, pt[1]), (-1, 0))
            else:
                pg.glabel(net, end, (-1, 0), 'input')
    pg.text('Inputs D2..D5 are pulled LOW by the ULN2803 when 24 V is present: use pinMode(pin, INPUT_PULLUP).',
            20.32, 160.0, 1.5)
    return pg


def page_outputs():
    pg = Page('Outputs', 'outputs.kicad_sch', 'A3', 'Outputs D8-D11', 4)
    pg.text('OUTPUTS D8..D11: one low-side MOSFET per channel, flyback clamp to +24V and drain-source TVS',
            20.32, 17.78, 2.0, True)
    chans = [('D11', 'Q4', 4), ('D10', 'Q3', 3), ('D9', 'Q2', 2), ('D8', 'Q1', 1)]   # J6 pin order
    J = pg.place('J6', 160.02, 144.78)
    X = 25.4
    cols = {0: 5.08, 1: 10.16, 2: 10.16, 3: 5.08}
    for r, (ch, q, n) in enumerate(chans):
        Gy = 66.04 + r * 60.96
        Y = Gy - 12.7
        led = 'LED%d' % (n + 1)
        pg.glabel(ch, (X, Gy), (-1, 0), 'input')
        A = (X + 12.7, Gy)
        B = (X + 25.4, Gy)
        pg.wire((X, Gy), A, B)
        pd = pg.place2('RN6', A[0], Gy + 8.89, ch, 'v')
        pg.wire(A, pd.pin([k for k, v in design.PARTS['RN6']['nets'].items() if v == ch][0]))
        pg.power('GND', [pd.pin(k) for k in (5, 6, 7, 8) if str(k) in {p['number'] for p in pd.pins}][0])
        rl = pg.place2('RN5', B[0], Gy + 8.89, ch, 'v')
        rl_top = rl.pin([k for k, v in design.PARTS['RN5']['nets'].items() if v == ch][0])
        rl_bot = rl.pin([k for k, v in design.PARTS['RN5']['nets'].items() if v == led + '_A'][0])
        pg.wire(B, rl_top)
        ld = pg.place2(led, B[0], Gy + 19.05, led + '_A', 'v')
        pg.wire(rl_bot, ld.pin(1))
        pg.power('GND', ld.pin(2))
        rg = pg.place2('RN3', X + 33.02, Gy, ch, 'h')
        rg_l = rg.pin([k for k, v in design.PARTS['RN3']['nets'].items() if v == ch][0])
        rg_r = rg.pin([k for k, v in design.PARTS['RN3']['nets'].items() if v == q + '_G'][0])
        pg.wire(B, rg_l)
        qq = pg.place(q, X + 45.72, Gy)
        pg.wire(rg_r, qq.pin(4))
        pg.power('GND', qq.pin(1))
        d = qq.pin(5)
        C = (X + 66.04, Y)
        pg.wire(d, (d[0], Y), C)
        pg.label('OUT_' + ch, (X + 55.88, Y), (1, 0))
        k = {'Q1': 1, 'Q2': 2, 'Q3': 3, 'Q4': 4}[q]
        tv = pg.place2('TVS%d' % k, C[0], Y + 7.62, 'OUT_' + ch, 'v')
        pg.wire(C, tv.pin(2))
        pg.power('GND', tv.pin(1))
        df = pg.place2('DF%d' % k, C[0], Y - 7.62, 'FB_' + ch, 'v')
        pg.wire(C, df.pin(2))
        dz = pg.place2('DZ%d' % k, C[0], Y - 19.05, '+24V', 'v')
        pg.wire(df.pin(1), dz.pin(1))
        pg.label('FB_' + ch, (C[0], (df.pin(1)[1] + dz.pin(1)[1]) / 2), (1, 0))
        pg.power('+24V', dz.pin(2))
        # to the output terminal
        jp = J.pin(r + 1)
        cx = jp[0] - cols[r]
        pg.wire(C, (cx, Y), (cx, jp[1]), jp)
    pg.text('J6: 1 = D11, 2 = D10, 3 = D9, 4 = D8', 170.18, 143.51, 1.5)
    pg.text('(load between machine +24V and the terminal)', 170.18, 147.32, 1.5)
    rating = [
        'Voltage rating check (per channel)',
        'Q: BSC0805LS, VDS max = 100 V, logic level (7 mOhm @ 10 V)',
        'Flyback at turn-off: drain -> SS56B (60 V) -> SMBJ15A (VBR 16.7-18.5 V, VC 24.4 V) -> +24V',
        '  drain is clamped at 24 + 0.7 + 24.4 = ~49 V (30 V supply: ~55 V) < 58 V TVS stand-off',
        'Drain-source TVS SMBJ58A: VRWM 58 V, VBR 64.4 V min, VC 93.6 V @ 6.4 A  <  100 V  -> OK',
        'Load current: 2 A per output, 5 A total (returns through J5 pins 2, 3, 4)',
    ]
    for i, s in enumerate(rating):
        pg.text(s, 200.66, 45.72 + i * 4.0, 1.5, i == 0)
    return pg


def page_inputs():
    pg = Page('Inputs', 'inputs.kicad_sch', 'A4', 'Inputs D2-D5', 5)
    pg.text('INPUTS 24V -> D2..D5: ULN2803 pulls the Arduino pin LOW, second channel drives the LED',
            20.32, 30.48, 2.0, True)
    u4 = pg.place('U4', 139.7, 101.6)
    pg.power('GND', u4.pin(9))
    pg.nc(u4.pin(10))
    j7 = pg.place('J7', 60.96, 101.6, rot=180)
    pairs = [('IN_D2', 4, (1, 2), 'RN1'), ('IN_D3', 3, (3, 4), 'RN1'),
             ('IN_D4', 2, (5, 6), 'RN4'), ('IN_D5', 1, (7, 8), 'RN4')]
    colx = {'IN_D2': None, 'IN_D3': 99.06, 'IN_D4': 93.98, 'IN_D5': 88.9}
    for net, jpin, ins, rn in pairs:
        lefts = []
        for i in ins:
            ip = u4.pin(i)
            r = pg.place2(rn, 116.84, ip[1], net, 'h', second_net='ULN_I%d' % i, fields='hide')
            nets = {str(k): v for k, v in design.PARTS[rn]['nets'].items()}
            rl = [q['number'] for q in r.pins if nets.get(q['number']) == net][0]
            rr = [q['number'] for q in r.pins if q['number'] != rl][0]
            pg.wire(r.pin(rr), ip)
            pg.wire(r.pin(rl), (110.49, ip[1]))
            lefts.append((110.49, ip[1]))
        pg.wire(lefts[0], lefts[1])
        jp = j7.pin(jpin)
        top = lefts[0]
        if colx[net] is None:
            pg.wire(top, jp)
        else:
            cx = colx[net]
            pg.wire(top, (cx, top[1]), (cx, jp[1]), jp)
        pg.label(net, (jp[0] + 2.54, jp[1]), (1, 0))
    # outputs
    for k, (o_d, o_led, dn, led) in enumerate([(18, 17, 'D2', 'LED6'), (16, 15, 'D3', 'LED7'),
                                               (14, 13, 'D4', 'LED8'), (12, 11, 'D5', 'LED9')]):
        p = u4.pin(o_d)
        pg.wire(p, (p[0] + 2.54, p[1]))
        pg.glabel(dn, (p[0] + 2.54, p[1]), (1, 0), 'output')
        p = u4.pin(o_led)
        cx = 172.72 + 15.24 * k
        ld = pg.place2(led, cx, 76.2, led + '_A', 'v')
        pg.wire(p, (cx, p[1]), ld.pin(2))
        r = pg.place2('RN2', cx, 64.77, '+5V', 'v', second_net=led + '_A')
        nets = {str(kk): v for kk, v in design.PARTS['RN2']['nets'].items()}
        rt = [q['number'] for q in r.pins if nets.get(q['number']) == '+5V'][0]
        rb = [q['number'] for q in r.pins if q['number'] != rt][0]
        pg.wire(r.pin(rb), ld.pin(1))
        pg.power('+5V', r.pin(rt))
    pg.text('J7: 1 = D5, 2 = D4, 3 = D3, 4 = D2 (24 V = active, reads LOW)', 30.48, 132.08, 1.5)
    pg.text('RN1, RN4: 4 x 10k (two 10k per input)', 86.36, 125.73, 1.5)
    return pg


def page_rs232():
    pg = Page('RS232', 'rs232.kicad_sch', 'A4', 'RS232', 6)
    pg.text('RS232 on D0/D1 (MAX232 + DB9 female)', 20.32, 30.48, 2.0, True)
    u2 = pg.place('U2', 101.6, 101.6)
    c1 = pg.place2('C1', 73.66, 82.55, 'C1P', 'v')
    pg.wire(c1.pin(2), u2.pin(1))
    pg.wire(c1.pin(1), u2.pin(3))
    c2 = pg.place2('C2', 129.54, 82.55, 'C2P', 'v')
    pg.wire(u2.pin(4), c2.pin(2))
    pg.wire(u2.pin(5), c2.pin(1))
    c4 = pg.place2('C4', 146.05, u2.pin(2)[1], 'VPOS', 'h', fields='above')
    pg.wire(u2.pin(2), c4.pin(1))
    pg.wire(c4.pin(2), (153.67, u2.pin(2)[1]))
    pg.power('+5V', (153.67, u2.pin(2)[1]))
    c3 = pg.place2('C3', 146.05, u2.pin(6)[1], 'VNEG', 'h', fields='above')
    pg.wire(u2.pin(6), c3.pin(2))
    pg.wire(c3.pin(1), (153.67, u2.pin(6)[1]))
    pg.power('GND', (153.67, u2.pin(6)[1]))
    pg.power('+5V', u2.pin(16))
    pg.power('GND', u2.pin(15))
    for n in (7, 8, 9, 10):
        pg.nc(u2.pin(n))
    # TX
    p = u2.pin(11)
    pg.wire(p, (p[0] - 7.62, p[1]))
    pg.glabel('D1_TX', (p[0] - 7.62, p[1]), (-1, 0), 'input')
    # RX through jumper JP1
    jp = pg.place('JP1', 60.96, 111.76, mirror=True)
    pg.wire(jp.pin(2), u2.pin(12))
    a = jp.pin(1)
    pg.wire(a, (a[0] + 2.54, a[1]), (a[0] + 2.54, 106.68), (50.8, 106.68))
    pg.glabel('D0_RX', (50.8, 106.68), (-1, 0), 'output')
    pg.text('JP1: remove while uploading a sketch over USB', 40.64, 128.27, 1.27)
    # DB9
    j8 = pg.place('J8', 185.42, 109.22)
    t = u2.pin(14)
    pg.wire(t, j8.pin(2))
    pg.label('RS232_TX', (t[0] + 5.08, t[1]), (1, 0))
    rr = u2.pin(13)
    pg.wire(rr, (167.64, rr[1]), (167.64, j8.pin(3)[1]), j8.pin(3))
    pg.label('RS232_RX', (rr[0] + 5.08, rr[1]), (1, 0))
    g = j8.pin(5)
    pg.wire(g, (g[0] - 2.54, g[1]))
    pg.power('GND', (g[0] - 2.54, g[1]))
    for n in (1, 4, 6, 7, 8, 9, 10, 11):
        pg.nc(j8.pin(n))
    pg.text('DB9 female: 2 = TX out, 3 = RX in, 5 = GND', 162.56, 137.16, 1.27)
    return pg


NOTES = [
    'UNO 24V shield v6 (KiCad), derived from EasyEDA v5 "uno glue controller single fet 231125"',
    'Removed: current sensing (INA180 x4, 20mR shunts RS8-RS11, R8-R11, C8-1..C11-1)',
    'Removed: glue-gun controller (Q5, L1, R15-R17, +48V, D8-4..D8-6)',
    'MOSFET sources go straight to GND; flyback clamps return to the board +24V',
    'New: input fuse F1 + TVS5 (surge / reverse polarity); J5 is 4-pin: +24V and three GND terminals',
    'Stock swaps: D1 PMEG3020EH -> DS210W, ULN2803 C2690548 -> ULN2803A C845537,',
    '  DB9 C86572 -> C53474757 (-JC), KF250-3.5-3P-1 -> KF250-3.5-3P-2 (same pins)',
    'Unchanged pin map: D8..D11 -> J6 pins 4..1, J7 pins 4..1 -> D2..D5, RS232 on D0/D1',
    'v5 reference designators are kept in each symbol field "v5 ref"',
]


def write_all():
    kicadlib.build_project_library()
    PWR_COUNTER[0] = 0
    pages = [page_power(), page_arduino(), page_outputs(), page_inputs(), page_rs232()]
    FP_PATHS.clear()
    for pg in pages:
        for ins in pg.insts:
            FP_PATHS.setdefault(ins.ref, '/%s/%s' % (pg.sheet_uuid, sym_uuid(ins.ref, 1 if ins.unit else 1)))
        pg.write()
    placed = {ins.ref for pg in pages for ins in pg.insts}
    missing = set(design.PARTS) - placed
    assert not missing, missing
    # root overview
    root = Page(None, PROJECT + '.kicad_sch', 'A4', 'Overview', 1)
    root.text('ARDUINO UNO 24V SHIELD v6 - overview', 20.32, 30.48, 2.5, True)
    sheets = []
    boxes = [(pages[0], 25.4, 45.72), (pages[1], 101.6, 45.72), (pages[2], 177.8, 45.72),
             (pages[3], 25.4, 81.28), (pages[4], 101.6, 81.28)]
    desc = {'Power': '24V in, fuse, TVS, 12V reg', 'Arduino': 'UNO headers, reset',
            'Outputs': 'D8-D11 MOSFET outputs', 'Inputs': '24V inputs -> D2-D5', 'RS232': 'MAX232 + DB9 on D0/D1'}
    for pg, x, y in boxes:
        w, h = 55.88, 20.32
        sheets.append(['sheet', ['at', x, y], ['size', w, h], ['exclude_from_sim', Sym('no')],
                       ['in_bom', Sym('yes')], ['on_board', Sym('yes')], ['dnp', Sym('no')],
                       ['fields_autoplaced', Sym('yes')], ['stroke', ['width', 0.1524], ['type', Sym('solid')]],
                       ['fill', ['color', 0, 0, 0, 0.0]], ['uuid', pg.sheet_uuid],
                       ['property', 'Sheetname', pg.name, ['at', x, y - 0.7116, 0], font(justify='left bottom')],
                       ['property', 'Sheetfile', pg.fname, ['at', x, y + h + 0.5884, 0],
                        font(justify='left top', hide=True)],
                       ['instances', ['project', PROJECT, ['path', '/' + ROOT, ['page', str(pg.page_no)]]]]])
        root.text(desc[pg.name], x + 2.54, y + 11.43, 1.5)
    for i, s in enumerate(NOTES):
        root.text(s, 20.32, 120.0 + i * 4.2, 1.5, i == 0)
    root.write(extra=sheets)
    return pages


def main():
    write_all()
    print('wrote schematic pages to', HW)


if __name__ == '__main__':
    main()
