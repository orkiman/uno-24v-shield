"""For every BOM line: is our footprint the one JLCPCB places the part with,
and does the pin JLCPCB/LCSC calls the cathode carry the net we intend?
Writes docs/reports/footprint_polarity_check.txt; exits non-zero on problems."""
import os
import sys

import design
import lcsc_fp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FPLIB = os.path.join(ROOT, 'hardware', 'lib', 'uno24v.pretty')

rows = lcsc_fp.check_parts(design.PARTS, FPLIB)
lines = []
bad = 0
for refs, code, fp, res, detail in rows:
    ok = res.startswith('footprint = JLCPCB') or res == 'footprint = JLCPCB'
    if res not in ('footprint = JLCPCB', 'same pads, numbering'):
        bad += 1
    lines.append('%-28s %-10s %-44s %-20s %s' % (','.join(refs), code, fp, res, detail))
out = os.path.join(ROOT, 'docs', 'reports', 'footprint_polarity_check.txt')
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, 'w', encoding='utf-8') as f:
    f.write('refs / LCSC / our footprint / result / polarity\n')
    f.write('\n'.join(lines) + '\n')
print('\n'.join(lines))
print('problems:', bad)
sys.exit(1 if bad else 0)
