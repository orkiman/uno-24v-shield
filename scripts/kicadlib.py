"""Helpers to pull symbols out of the KiCad standard libraries and build the
project symbol library (lib/uno24v.kicad_sym)."""
import copy
import os
import sexp
from sexp import Sym, find, find1

STD_SYM_DIR = os.environ.get('KICAD9_SYMBOL_DIR', '/usr/share/kicad/symbols')
HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.join(os.path.dirname(HERE), 'hardware')
PROJ_SYM_LIB = os.path.join(PROJ, 'lib', 'uno24v.kicad_sym')

_cache = {}


def _lib(path):
    if path not in _cache:
        _cache[path] = sexp.parse(open(path, encoding='utf-8').read())
    return _cache[path]


def _rename(sym, new):
    """rename a library symbol and its unit sub-symbols"""
    old = sym[1]
    sym = copy.deepcopy(sym)
    sym[1] = new
    for s in find(sym, 'symbol'):
        if s[1].startswith(old + '_'):
            s[1] = new + s[1][len(old):]
    return sym


def get_symbol(lib_id):
    """return a flattened symbol s-expr named exactly like its lib item name"""
    lib, name = lib_id.split(':')
    path = PROJ_SYM_LIB if lib == 'uno24v' else os.path.join(STD_SYM_DIR, lib + '.kicad_sym')
    tree = _lib(path)
    syms = {s[1]: s for s in find(tree, 'symbol')}
    s = syms[name]
    ext = find1(s, 'extends')
    if ext:
        base = _rename(get_symbol(lib + ':' + ext[1]), name)
        props = {p[1]: p for p in find(s, 'property')}
        out = [x for x in base if not (isinstance(x, list) and x and x[0] == 'property' and x[1] in props)]
        # insert child properties right after the header items
        idx = next(i for i, x in enumerate(out) if isinstance(x, list) and x[0] == 'property') if any(
            isinstance(x, list) and x and x[0] == 'property' for x in out) else 2
        for p in reversed(list(props.values())):
            out.insert(idx, copy.deepcopy(p))
        return out
    return copy.deepcopy(s)


def pins(sym):
    """list of dict(number, name, type, x, y, angle, length, hidden)"""
    out = []

    def walk(e):
        for x in e:
            if isinstance(x, list) and x and x[0] == 'pin':
                at = find1(x, 'at')
                hide = any((isinstance(y, list) and y[0] == 'hide' and (len(y) < 2 or y[1] == 'yes')) or y == 'hide'
                           for y in x)
                out.append(dict(number=str(find1(x, 'number')[1]), name=str(find1(x, 'name')[1]), type=str(x[1]),
                                x=float(at[1]), y=float(at[2]), angle=float(at[3]) if len(at) > 3 else 0.0,
                                length=float(find1(x, 'length')[1]), hidden=hide))
            elif isinstance(x, list):
                walk(x)
    walk(sym)
    return out


def _set_prop(sym, key, value):
    for p in find(sym, 'property'):
        if p[1] == key:
            p[2] = value
            return
    sym.insert(3, ['property', key, value, ['at', 0, 0, 0], ['effects', ['font', ['size', 1.27, 1.27]], ['hide', Sym('yes')]]])


def _renumber(sym, mapping):
    def walk(e):
        for x in e:
            if isinstance(x, list) and x and x[0] == 'pin':
                n = find1(x, 'number')
                if str(n[1]) in mapping:
                    n[1] = mapping[str(n[1])]
            elif isinstance(x, list):
                walk(x)
    walk(sym)


def _pin(num, name, typ, x, y, ang, length=2.54, hide=False):
    e = ['pin', Sym(typ), Sym('line'), ['at', x, y, ang], ['length', length]]
    if hide:
        e.append(['hide', Sym('yes')])
    e += [['name', name, ['effects', ['font', ['size', 1.27, 1.27]]]],
          ['number', num, ['effects', ['font', ['size', 1.27, 1.27]]]]]
    return e


def build_project_library():
    syms = []

    # LED with pad 1 = anode (LCSC LED0603-FD / 19-219 footprints)
    s = _rename(get_symbol('Device:LED'), 'LED_A1K2')
    _renumber(s, {'1': '2', '2': '1'})
    _set_prop(s, 'Description', 'LED, pin 1 = anode, pin 2 = cathode (LCSC footprint numbering)')
    syms.append(s)

    # Unidirectional TVS with pin 1 = anode (LCSC SMBJ58A C41376102 footprint)
    s = _rename(get_symbol('Device:D_Zener'), 'D_TVS_A1K2')
    _renumber(s, {'1': '2', '2': '1'})
    _set_prop(s, 'Reference', 'D')
    _set_prop(s, 'Description', 'Unidirectional TVS diode, pin 1 = anode, pin 2 = cathode')
    syms.append(s)

    # BSC0805LS: Infineon PG-TDSON-8, pads 1-3 S, 4 G, 5-8 + exposed pad 9 = D
    s = _rename(get_symbol('Transistor_FET:BSC040N10NS5'), 'BSC0805LS')
    _set_prop(s, 'Value', 'BSC0805LS')
    _set_prop(s, 'Footprint', '')
    _set_prop(s, 'Datasheet', 'https://www.infineon.com/part/BSC0805LS')
    _set_prop(s, 'Description', 'N-MOSFET 100V 61A 7mOhm@10V logic level, PG-TDSON-8')
    unit = [u for u in find(s, 'symbol') if u[1].endswith('_1_1')][0]
    for n in ('6', '7', '8', '9'):
        unit.append(_pin(n, 'D', 'passive', 2.54, 5.08, 270, 2.54, hide=True))
    syms.append(s)

    # DB9 female with mounting holes as pads 10/11 (LCSC footprint numbering)
    s = _rename(get_symbol('Connector:DE9_Socket_MountingHoles'), 'DB9_Female_MH')
    _renumber(s, {'0': '10'})
    mh = [p for p in pins(s) if p['number'] == '10'][0]
    unit = [u for u in find(s, 'symbol') if u[1].endswith('_1_1')][0]
    unit.append(_pin('11', mh['name'], mh['type'], mh['x'] + 2.54, mh['y'], mh['angle'], mh['length']))
    syms.append(s)

    # 78M12 regulator, TO-252: 1 IN, 2 GND (tab), 3 OUT
    s = ['symbol', '78M12',
         ['pin_names', ['offset', 0.254]],
         ['exclude_from_sim', Sym('no')], ['in_bom', Sym('yes')], ['on_board', Sym('yes')],
         ['property', 'Reference', 'U', ['at', 0, 6.35, 0], ['effects', ['font', ['size', 1.27, 1.27]]]],
         ['property', 'Value', '78M12', ['at', 0, 3.81, 0], ['effects', ['font', ['size', 1.27, 1.27]]]],
         ['property', 'Footprint', '', ['at', 0, 0, 0], ['effects', ['font', ['size', 1.27, 1.27]], ['hide', Sym('yes')]]],
         ['property', 'Datasheet', '', ['at', 0, 0, 0], ['effects', ['font', ['size', 1.27, 1.27]], ['hide', Sym('yes')]]],
         ['property', 'Description', 'Positive 12V 500mA linear regulator, TO-252',
          ['at', 0, 0, 0], ['effects', ['font', ['size', 1.27, 1.27]], ['hide', Sym('yes')]]],
         ['symbol', '78M12_0_1',
          ['rectangle', ['start', -5.08, 2.54], ['end', 5.08, -5.08],
           ['stroke', ['width', 0.254], ['type', Sym('default')]], ['fill', ['type', Sym('background')]]]],
         ['symbol', '78M12_1_1',
          _pin('1', 'IN', 'power_in', -7.62, 0, 0),
          _pin('2', 'GND', 'power_in', 0, -7.62, 90),
          _pin('3', 'OUT', 'power_out', 7.62, 0, 180)],
         ['embedded_fonts', Sym('no')]]
    syms.append(s)

    lib = ['kicad_symbol_lib', ['version', 20241209], ['generator', 'uno24v_scripts'],
           ['generator_version', '9.0']] + syms
    os.makedirs(os.path.dirname(PROJ_SYM_LIB), exist_ok=True)
    with open(PROJ_SYM_LIB, 'w', encoding='utf-8') as f:
        f.write(sexp.dump(lib) + '\n')
    _cache.pop(PROJ_SYM_LIB, None)


if __name__ == '__main__':
    build_project_library()
    for n in ('LED_A1K2', 'D_TVS_A1K2', 'BSC0805LS', 'DB9_Female_MH', '78M12'):
        print(n, [(p['number'], p['name']) for p in pins(get_symbol('uno24v:' + n))])
