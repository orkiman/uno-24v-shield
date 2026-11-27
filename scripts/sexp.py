"""Minimal S-expression reader/writer for KiCad files."""
import re

_tok = re.compile(r'\s*(\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+)')


class Sym(str):
    """Unquoted atom."""


def parse(text):
    pos = 0
    stack = [[]]
    n = len(text)
    while pos < n:
        m = _tok.match(text, pos)
        if not m:
            if text[pos:].strip() == '':
                break
            raise ValueError('parse error at %d' % pos)
        t = m.group(1)
        pos = m.end()
        if t == '(':
            stack.append([])
        elif t == ')':
            e = stack.pop()
            stack[-1].append(e)
        elif t.startswith('"'):
            stack[-1].append(t[1:-1].replace('\\"', '"').replace('\\\\', '\\'))
        else:
            stack[-1].append(Sym(t))
    return stack[0][0]


def q(s):
    return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"'


def dump(e, indent=0):
    if isinstance(e, list):
        if not e:
            return '()'
        head = str(e[0]) if isinstance(e[0], str) else dump(e[0])
        simple = all(not isinstance(x, list) for x in e)
        if simple:
            return '(' + ' '.join([head] + [dump(x) for x in e[1:]]) + ')'
        out = '(' + head
        for x in e[1:]:
            if isinstance(x, list):
                out += '\n' + '\t' * (indent + 1) + dump(x, indent + 1)
            else:
                out += ' ' + dump(x)
        return out + '\n' + '\t' * indent + ')'
    if isinstance(e, Sym):
        return str(e)
    if isinstance(e, bool):
        return 'yes' if e else 'no'
    if isinstance(e, (int, float)):
        if isinstance(e, float):
            s = ('%.4f' % e).rstrip('0').rstrip('.')
            return s if s not in ('-0', '') else '0'
        return str(e)
    return q(e)


def find(e, key):
    return [x for x in e if isinstance(x, list) and x and x[0] == key]


def find1(e, key):
    r = find(e, key)
    return r[0] if r else None
