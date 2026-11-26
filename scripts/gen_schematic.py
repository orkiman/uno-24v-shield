"""Generate hardware/uno-24v-shield.kicad_sch from design.py.

Every used pin gets a short wire stub ending in a net label (or a power
symbol for GND/+5V/+24V); unused pins get a no-connect flag.  This keeps the
schematic 100% consistent with design.py, which is what the PCB is checked
against (DRC schematic parity)."""
import math
import os
import uuid as _uuid

import design
import kicadlib
import sexp
from sexp import Sym

PROJECT = 'uno-24v-shield'
OUT = os.path.join(kicadlib.PROJ, PROJECT + '.kicad_sch')
NS = _uuid.UUID('6f1c2a52-6d1e-4a7e-9b1f-2d0c5e1a7b00')
STUB = 2.54


def uid(*key):
    return str(_uuid.uuid5(NS, '/'.join(str(k) for k in key)))


ROOT = uid('root')


def snap(v):
    return round(v / 1.27) * 1.27


def xf(px, py, rot):
    """library point -> screen offset (y down) for symbol rotation rot (CCW)"""
    r = math.radians(rot)
    x = px * math.cos(r) - py * math.sin(r)
    y = px * math.sin(r) + py * math.cos(r)
    return round(x, 4), round(-y, 4)


def outward(angle, rot):
    """screen unit vector pointing away from the symbol body for a pin"""
    a = math.radians(angle + 180 + rot)
    return round(math.cos(a)), round(-math.sin(a))


def font(size=1.27, **kw):
    e = ['effects', ['font', ['size', size, size]] + ([['bold', Sym('yes')]] if kw.get('bold') else [])]
    if kw.get('justify'):
        e.append(['justify'] + [Sym(j) for j in kw['justify'].split()])
    if kw.get('hide'):
        e.append(['hide', Sym('yes')])
    return e


def prop(key, val, x, y, ang=0, hide=False, justify=None, size=1.27):
    return ['property', key, val, ['at', round(x, 3), round(y, 3), ang], font(size, hide=hide, justify=justify)]


def field_pos(p, pl, rot, x0, y0):
    """reference/value positions that stay clear of pins, stubs and labels"""
    pts = [xf(q['x'], q['y'], rot) for q in pl]
    xs = [a for a, b in pts]
    ys = [b for a, b in pts]
    sides = set()
    for q in pl:
        dx, dy = outward(q['angle'], rot)
        sides.add((dx, dy))
    sym = p['sym']
    if (0, -1) in sides and (0, 1) in sides and (1, 0) not in sides:
        # vertical part (2-pin rotated, resistor packs): fields on the right
        x = x0 + max(xs + [0]) + (2.54 if len(pl) > 2 else 2.0)
        return snap(x), y0 - 1.27, snap(x), y0 + 1.27, 'left'
    if 'BSC0805LS' in sym:
        return x0 + 5.08, y0 - 1.27, x0 + 5.08, y0 + 1.27, 'left'
    if sides <= {(1, 0), (-1, 0)} and len(pl) == 2:
        # horizontal 2-pin: above / below the body
        return x0, y0 - 3.81, x0, y0 + 3.81, 'center' if False else 'left'
    # connectors / ICs: above the top-most pin, left aligned to the body
    top = min(ys)
    x = x0 + (min(xs) if (-1, 0) not in sides else 0) - (2.54 if (-1, 0) in sides and (1, 0) in sides else 0)
    if (0, -1) in sides:            # pins sticking out of the top (IC supply)
        x = x0 + max(xs) - 2.54
        return x, y0 + top + 1.27, x, y0 + top + 3.3, 'left'
    top = min(top, -2.54)
    return x0 - 1.27, y0 + top - 5.3, x0 - 1.27, y0 + top - 3.2, 'left'


class Sheet:
    def __init__(self):
        self.items = []
        self.lib_ids = set()
        self.pwr_n = 0
        self.pin_xy = {}

    def links(self):
        for a, b in design.LINKS:
            (x1, y1) = self.pin_xy[(a[0], str(a[1]))]
            (x2, y2) = self.pin_xy[(b[0], str(b[1]))]
            if x1 != x2 and y1 != y2:
                self.wire(x1, y1, x1, y2)
                self.wire(x1, y2, x2, y2)
            else:
                self.wire(x1, y1, x2, y2)
            net = design.PARTS[a[0]]['nets'][a[1]]
            assert net == design.PARTS[b[0]]['nets'][b[1]]
            mx, my = snap(x1), snap((y1 + y2) / 2)
            self.label(net, mx, my, 1, 0)

    def wire(self, x1, y1, x2, y2):
        self.items.append(['wire', ['pts', ['xy', round(x1, 3), round(y1, 3)], ['xy', round(x2, 3), round(y2, 3)]],
                           ['stroke', ['width', 0], ['type', Sym('default')]], ['uuid', uid('w', x1, y1, x2, y2)]])

    def label(self, net, x, y, dx, dy):
        ang = {(1, 0): 0, (-1, 0): 180, (0, -1): 90, (0, 1): 270}[(dx, dy)]
        just = 'left bottom' if ang in (0, 90) else 'right bottom'
        self.items.append(['label', net, ['at', round(x, 3), round(y, 3), ang],
                           ['fields_autoplaced', Sym('yes')], font(justify=just), ['uuid', uid('l', net, x, y)]])

    def noconnect(self, x, y):
        self.items.append(['no_connect', ['at', round(x, 3), round(y, 3)], ['uuid', uid('nc', x, y)]])

    def text(self, s, x, y, size=1.27, bold=False):
        self.items.append(['text', s, ['exclude_from_sim', Sym('no')], ['at', x, y, 0],
                           font(size, bold=bold, justify='left bottom'), ['uuid', uid('t', s, x, y)]])

    def power(self, lib_id, x, y, dx, dy):
        """power symbol whose pin sits at (x,y), body pointing along (dx,dy)"""
        self.lib_ids.add(lib_id)
        self.pwr_n += 1
        ref = '#PWR%03d' % self.pwr_n if 'FLAG' not in lib_id else '#FLG%03d' % self.pwr_n
        gnd_like = lib_id == 'power:GND'
        # GND body points down at rot 0, supply symbols point up at rot 0
        base = (0, 1) if gnd_like else (0, -1)
        rot = {((0, 1), (0, 1)): 0, ((0, 1), (1, 0)): 90, ((0, 1), (0, -1)): 180, ((0, 1), (-1, 0)): 270,
               ((0, -1), (0, -1)): 0, ((0, -1), (-1, 0)): 90, ((0, -1), (0, 1)): 180, ((0, -1), (1, 0)): 270}[(base, (dx, dy))]
        name = lib_id.split(':')[1]
        if dx:
            vx, vy = x + dx * 4.4, y
            vjust = 'left' if dx > 0 else 'right'
        else:
            vx, vy = x, y + dy * 3.4 + (0.6 if dy > 0 else 0)
            vjust = None
        u = uid('pwr', ref, x, y)
        self.items.append(['symbol', ['lib_id', lib_id], ['at', round(x, 3), round(y, 3), rot], ['unit', 1],
                           ['exclude_from_sim', Sym('no')], ['in_bom', Sym('yes')], ['on_board', Sym('yes')],
                           ['dnp', Sym('no')], ['uuid', u],
                           prop('Reference', ref, x, y, hide=True),
                           prop('Value', name, vx, vy, justify=vjust),
                           prop('Footprint', '', x, y, hide=True),
                           prop('Datasheet', '', x, y, hide=True),
                           prop('Description', '', x, y, hide=True),
                           ['pin', '1', ['uuid', uid('pwrpin', ref)]],
                           ['instances', ['project', PROJECT, ['path', '/' + ROOT, ['reference', ref], ['unit', 1]]]]])

    def part(self, p):
        lib_id = p['sym']
        self.lib_ids.add(lib_id)
        sym = kicadlib.get_symbol(lib_id)
        rot = p.get('rot', 0)
        x0, y0 = p['pos']
        props = [prop('Reference', p['ref'], x0 + 4.0, y0 - 6.0, justify='left'),
                 prop('Value', p['value'], x0 + 4.0, y0 - 4.0, justify='left'),
                 prop('Footprint', design.FP_LIB + ':' + p['fp'], x0, y0, hide=True),
                 prop('Datasheet', '', x0, y0, hide=True),
                 prop('Description', p['desc'], x0, y0, hide=True),
                 prop('LCSC', p['lcsc'], x0, y0, hide=True),
                 prop('MPN', p['mpn'], x0, y0, hide=True),
                 prop('v5 ref', p['old'], x0, y0, hide=True)]
        pl = kicadlib.pins(sym)
        rx, ry, vx, vy, just = field_pos(p, pl, rot, x0, y0)
        fa = rot % 180  # KiCad draws fields relative to the symbol rotation
        props[0][3] = ['at', rx, ry, fa]
        if rot in (90, 180) and just == 'left':
            just = 'right'  # justification is mirrored with the symbol
        props[0][4] = font(justify=just)
        props[1][3] = ['at', vx, vy, fa]
        props[1][4] = font(justify=just)
        inst = ['symbol', ['lib_id', lib_id], ['at', x0, y0, rot], ['unit', 1],
                ['exclude_from_sim', Sym('no')], ['in_bom', Sym('yes')], ['on_board', Sym('yes')],
                ['dnp', Sym('no')], ['fields_autoplaced', Sym('yes')], ['uuid', uid('sym', p['ref'])]] + props
        seen = set()
        for q in pl:
            inst.append(['pin', q['number'], ['uuid', uid('pin', p['ref'], q['number'])]])
        inst.append(['instances', ['project', PROJECT, ['path', '/' + ROOT, ['reference', p['ref']], ['unit', 1]]]])
        self.items.append(inst)

        nets = {str(k): v for k, v in p['nets'].items()}
        linked = {str(pin) for (r1, p1), (r2, p2) in design.LINKS for r, pin in ((r1, p1), (r2, p2)) if r == p['ref']}
        for q in pl:
            if q['number'] in linked:
                ox, oy = xf(q['x'], q['y'], rot)
                self.pin_xy[(p['ref'], q['number'])] = (snap(x0 + ox), snap(y0 + oy))
                continue
            ox, oy = xf(q['x'], q['y'], rot)
            px, py = snap(x0 + ox), snap(y0 + oy)
            key = (px, py)
            if key in seen:      # stacked (hidden) pins share the visible pin's stub
                continue
            seen.add(key)
            net = nets.get(q['number'])
            if net is None:
                # stacked pins: any pin at this location with a net?
                for q2 in pl:
                    o2 = xf(q2['x'], q2['y'], rot)
                    if (snap(x0 + o2[0]), snap(y0 + o2[1])) == key and nets.get(q2['number']):
                        net = nets[q2['number']]
            if net is None:
                self.noconnect(px, py)
                continue
            dx, dy = outward(q['angle'], rot)
            ex, ey = px + dx * STUB, py + dy * STUB
            self.wire(px, py, ex, ey)
            if net in design.POWER_SYMBOL_NETS and not (dx and len(pl) > 2):
                self.power(design.POWER_SYMBOL_NETS[net], ex, ey, dx, dy)
            else:
                self.label(net, ex, ey, dx, dy)

    def pwr_flag(self, net, x, y):
        """PWR_FLAG on a net: flag at (x,y), wire down 2.54, then label / power symbol"""
        self.power('power:PWR_FLAG', x, y, 0, -1)
        self.wire(x, y, x, y + 2.54)
        if net in design.POWER_SYMBOL_NETS:
            self.power(design.POWER_SYMBOL_NETS[net], x, y + 2.54, 0, 1 if net == 'GND' else -1)
            if net != 'GND':  # supply symbols point up; move flag stub sideways
                pass
        else:
            self.label(net, x, y + 2.54, 1, 0)


def lib_symbols(ids):
    out = ['lib_symbols']
    for lib_id in sorted(ids):
        s = kicadlib.get_symbol(lib_id)
        s[1] = lib_id
        out.append(s)
    return out


NOTES = [
    'UNO 24V shield v6 (KiCad), derived from EasyEDA v5 "uno glue controller single fet 231125"',
    'Removed: current sensing (INA180 x4, 20mR shunts RS8-RS11, R8-R11, C8-1..C11-1)',
    'Removed: glue-gun controller (Q5, L1, R15-R17, +48V, D8-4..D8-6)',
    'MOSFET sources go straight to GND; J5 pin 3 (old "VL+") is now +24V on the board',
    'Stock swaps: D1 PMEG3020EH -> DS210W, ULN2803 C2690548 -> ULN2803A C845537,',
    '  DB9 C86572 -> C53474757 (-JC), KF250-3.5-3P-1 -> KF250-3.5-3P-2 (same pins)',
    'Unchanged pin map: D8..D11 -> J6 pins 4..1, J7 pins 4..1 -> D2..D5,',
    '  RS232 on D0/D1 via MAX232 + DB9 (remove JP1 while uploading)',
    'v5 reference designators are kept in each symbol field "v5 ref"',
]
RATING = [
    'Voltage rating check (per channel)',
    'Q: BSC0805LS, VDS max = 100 V',
    'Flyback: drain -> SS56B (60 V) -> SMBJ15A (VBR 16.7-18.5 V, VC 24.4 V) -> +24V',
    '  drain clamps at 24 + 0.7 + 24.4 = ~49 V (30 V supply: ~55 V) < 58 V TVS stand-off',
    'D-S TVS SMBJ58A: VRWM 58 V, VBR 64.4 V min, VC 93.6 V @ 6.4 A  <  100 V  -> OK',
]


def main():
    kicadlib.build_project_library()
    sh = Sheet()
    for p in design.PARTS.values():
        sh.part(p)
    sh.links()
    # power flags
    fx = 20.32
    for i, n in enumerate(design.PWR_FLAG_NETS):
        sh.pwr_flag(n, 63.5 + i * 12.7, 25.4)
    sh.text('Power flags', 63.5, 20.32, 1.5, True)

    # block titles
    for t, x, y in [('POWER INPUT 24V -> 12V (Arduino VIN)', 30.48, 38.1),
                    ('ARDUINO UNO HEADERS', 30.48, 93.98),
                    ('OUTPUTS D8..D11 (low-side MOSFET, flyback + TVS)', 172.72, 20.32),
                    ('INPUTS 24V -> D2..D5 (ULN2803 + LEDs)', 172.72, 182.88),
                    ('RS232 on D0/D1 (MAX232)', 50.8, 195.58)]:
        sh.text(t, x, y, 2.0, True)
    y = 129.54
    for i, s in enumerate(NOTES):
        sh.text(s, 279.4, y, 1.4, i == 0)
        y += 3.0
    y += 3.0
    for i, s in enumerate(RATING):
        sh.text(s, 279.4, y, 1.4, i == 0)
        y += 3.0

    doc = ['kicad_sch', ['version', 20250114], ['generator', 'eeschema'], ['generator_version', '9.0'],
           ['uuid', ROOT], ['paper', 'A3'],
           ['title_block', ['title', 'Arduino UNO 24V Shield'], ['date', '2026-11-26'], ['rev', '6.0'],
            ['company', ''], ['comment', 1, 'Outputs D8-D11, inputs D2-D5, RS232 D0/D1'],
            ['comment', 2, 'Derived from EasyEDA v5 (2025-10-22); current sense and glue controller removed']],
           lib_symbols(sh.lib_ids)] + sh.items + [
        ['sheet_instances', ['path', '/', ['page', '1']]],
        ['embedded_fonts', Sym('no')]]
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(sexp.dump(doc) + '\n')
    print('wrote', OUT)


if __name__ == '__main__':
    main()
