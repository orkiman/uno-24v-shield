"""Produce the JLCPCB order package and review documents.

fab/   gerber zip (+ unzipped gerber/ for inspection), BOM and CPL in JLCPCB format
docs/  schematic PDF, PCB PDF, PNG renders, ERC/DRC reports
"""
import csv
import os
import re
import shutil
import subprocess
import zipfile

import design

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HW = os.path.join(ROOT, 'hardware')
NAME = 'uno-24v-shield'
VER = 'v6'
PCB = os.path.join(HW, NAME + '.kicad_pcb')
SCH = os.path.join(HW, NAME + '.kicad_sch')
FAB = os.path.join(ROOT, 'fab')
DOCS = os.path.join(ROOT, 'docs')


def run(*args):
    r = subprocess.run(['kicad-cli'] + list(args), capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit('kicad-cli failed: %s\n%s\n%s' % (' '.join(args), r.stdout, r.stderr))
    return r.stdout


def natkey(ref):
    m = re.match(r'([A-Za-z]+)(\d+)', ref)
    return (m.group(1), int(m.group(2))) if m else (ref, 0)


def gerbers():
    gdir = os.path.join(FAB, 'gerber')
    shutil.rmtree(gdir, ignore_errors=True)
    os.makedirs(gdir)
    run('pcb', 'export', 'gerbers', '-o', gdir,
        '--layers', 'F.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts',
        '--subtract-soldermask', '--no-x2', '--no-netlist', PCB)
    run('pcb', 'export', 'drill', '-o', gdir + '/', '--format', 'excellon', '--excellon-units', 'mm',
        '--excellon-zeros-format', 'decimal', '--excellon-oval-format', 'alternate',
        '--excellon-separate-th', '--generate-map', '--map-format', 'gerberx2', PCB)
    z = os.path.join(FAB, '%s-%s_gerbers.zip' % (NAME, VER))
    with zipfile.ZipFile(z, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fn in sorted(os.listdir(gdir)):
            zf.write(os.path.join(gdir, fn), fn)
    return z, sorted(os.listdir(gdir))


def bom():
    groups = {}
    for ref, p in design.PARTS.items():
        key = (p['lcsc'], p['fp'])
        groups.setdefault(key, []).append(ref)
    fn = os.path.join(FAB, '%s-%s_BOM_JLCPCB.csv' % (NAME, VER))
    rows = []
    for (lcsc, fp), refs in groups.items():
        refs.sort(key=natkey)
        p = design.PARTS[refs[0]]
        desc = p['desc']
        if len(refs) > 1:  # drop the per-channel part of the description
            desc = re.sub(r',? ?output D\d+$| \(above terminal .*\)$', '', desc)
            desc = re.sub(r'^(Output|Input) D\d+ indicator', r'\1 indicators', desc)
        rows.append([p['mpn'] if p['mpn'] else p['value'], ','.join(refs), fp, lcsc, len(refs), desc,
                     'THT' if any(design.PARTS[r]['fp'].startswith(('CONN-TH', 'HDR-TH', 'DSUB-TH')) for r in refs) else 'SMD'])
    rows.sort(key=lambda r: natkey(r[1].split(',')[0]))
    with open(fn, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['Comment', 'Designator', 'Footprint', 'LCSC Part #', 'Qty', 'Description', 'Mount'])
        w.writerows(rows)
    return fn, rows


def cpl():
    tmp = os.path.join(FAB, '_pos.csv')
    run('pcb', 'export', 'pos', '-o', tmp, '--side', 'both', '--format', 'csv', '--units', 'mm', PCB)
    fn = os.path.join(FAB, '%s-%s_CPL_JLCPCB.csv' % (NAME, VER))
    rows = []
    with open(tmp, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            rot = float(r['Rot']) % 360
            rows.append([r['Ref'], '%.4fmm' % float(r['PosX']), '%.4fmm' % float(r['PosY']),
                         'Top' if r['Side'].lower().startswith('top') else 'Bottom', '%g' % rot])
    os.remove(tmp)
    rows.sort(key=lambda r: natkey(r[0]))
    refs = {r[0] for r in rows}
    missing = set(design.PARTS) - refs
    assert not missing, missing
    with open(fn, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['Designator', 'Mid X', 'Mid Y', 'Layer', 'Rotation'])
        w.writerows(rows)
    return fn, rows


def docs():
    os.makedirs(DOCS, exist_ok=True)
    run('sch', 'export', 'pdf', '-o', os.path.join(DOCS, '%s-%s_schematic.pdf' % (NAME, VER)), SCH)
    pages = [('top', 'F.Cu,F.Silkscreen,F.Mask,Edge.Cuts'),
             ('bottom', 'B.Cu,B.Silkscreen,B.Mask,Edge.Cuts'),
             ('assembly-top', 'F.Fab,F.Silkscreen,Edge.Cuts')]
    tmpd = os.path.join(DOCS, '_tmp')
    os.makedirs(tmpd, exist_ok=True)
    pdfs = []
    for name, layers in pages:
        out = os.path.join(tmpd, name + '.pdf')
        extra = ['--mirror'] if name == 'bottom' else []
        run('pcb', 'export', 'pdf', '-o', out, '--layers', layers, '--include-border-title', *extra, PCB)
        pdfs.append(out)
    merged = os.path.join(DOCS, '%s-%s_pcb.pdf' % (NAME, VER))
    if shutil.which('pdfunite'):
        subprocess.run(['pdfunite'] + pdfs + [merged], check=True)
    else:
        try:
            from pypdf import PdfWriter
            w = PdfWriter()
            for p in pdfs:
                w.append(p)
            w.write(merged)
        except ImportError:
            for p in pdfs:
                shutil.copy(p, os.path.join(DOCS, '%s-%s_pcb_%s.pdf' % (NAME, VER, os.path.basename(p)[:-4])))
    shutil.rmtree(tmpd)
    for side in ('top', 'bottom'):
        run('pcb', 'render', '-o', os.path.join(DOCS, '%s-%s_render_%s.png' % (NAME, VER, side)),
            '--side', side, '--width', '2400', '--height', '1600', '--quality', 'high', '--background', 'opaque', PCB)
    # reports
    rep = os.path.join(DOCS, 'reports')
    os.makedirs(rep, exist_ok=True)
    subprocess.run(['kicad-cli', 'sch', 'erc', '--severity-all', '-o', os.path.join(rep, 'erc.rpt'), SCH], capture_output=True)
    subprocess.run(['kicad-cli', 'pcb', 'drc', '--schematic-parity', '--severity-all', '-o', os.path.join(rep, 'drc.rpt'), PCB],
                   capture_output=True)


if __name__ == '__main__':
    os.makedirs(FAB, exist_ok=True)
    z, files = gerbers()
    print('gerbers:', z, files)
    b, rows = bom()
    print('bom:', b, len(rows), 'lines')
    c, crow = cpl()
    print('cpl:', c, len(crow), 'parts')
    docs()
    print('docs written to', DOCS)
