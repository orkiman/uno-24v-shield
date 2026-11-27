"""Draw docs/uno-24v-shield-v6_polarity.png: top view of the board (same
orientation as the JLCPCB preview) with every polarity-sensitive part
highlighted: cathode pad = red "K", pin 1 of ICs / MOSFETs = blue "1".
Compare each highlighted pad with the polarity mark JLCPCB shows on the part."""
import os
import sys

import pcbnew
from PIL import Image, ImageDraw, ImageFont

import design

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PCB = os.path.join(ROOT, 'hardware', 'uno-24v-shield.kicad_pcb')
OUT = os.path.join(ROOT, 'docs', 'uno-24v-shield-v6_polarity.png')
S = 30.0          # px per mm
M = 60            # margin px
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONTB = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'

PIN1 = {'Q1', 'Q2', 'Q3', 'Q4', 'U2', 'U3', 'U4'}


def main():
    b = pcbnew.LoadBoard(PCB)
    bb = b.GetBoardEdgesBoundingBox()
    x0, y0 = bb.GetX() / 1e6, bb.GetY() / 1e6
    W = int(bb.GetWidth() / 1e6 * S) + 2 * M
    H = int(bb.GetHeight() / 1e6 * S) + 2 * M + 170
    img = Image.new('RGB', (W, H), 'white')
    d = ImageDraw.Draw(img)
    f_small = ImageFont.truetype(FONT, 14)
    f_ref = ImageFont.truetype(FONTB, 18)
    f_k = ImageFont.truetype(FONTB, 22)
    f_title = ImageFont.truetype(FONTB, 26)

    def px(x, y):
        return (M + (x - x0) * S, M + (y - y0) * S)

    d.rectangle([px(x0, y0), px(x0 + bb.GetWidth() / 1e6, y0 + bb.GetHeight() / 1e6)], outline='black', width=3)
    marked = []
    for f in b.GetFootprints():
        ref = f.GetReference()
        p = design.PARTS.get(ref, {})
        hot = ref in design.CATHODE or ref in PIN1
        # courtyard / body
        c = f.GetCourtyard(pcbnew.F_CrtYd)
        cb = c.BBox() if c.OutlineCount() else f.GetBoundingBox(False)
        d.rectangle([px(cb.GetX() / 1e6, cb.GetY() / 1e6), px(cb.GetRight() / 1e6, cb.GetBottom() / 1e6)],
                    outline=(230, 150, 0) if hot else (200, 200, 200), width=3 if hot else 1)
        kpad = None
        if ref in design.CATHODE:
            kn = [k for k, v in p['nets'].items() if v == design.CATHODE[ref]]
            kpad = str(kn[0])
        elif ref in PIN1:
            kpad = '1'
        for pad in f.Pads():
            bx = pad.GetBoundingBox()
            box = [px(bx.GetX() / 1e6, bx.GetY() / 1e6), px(bx.GetRight() / 1e6, bx.GetBottom() / 1e6)]
            if kpad is not None and pad.GetNumber() == kpad:
                col = (220, 0, 0) if ref in design.CATHODE else (0, 70, 220)
                d.rectangle(box, fill=col)
                cx, cy = px(pad.GetPosition().x / 1e6, pad.GetPosition().y / 1e6)
                txt = 'K' if ref in design.CATHODE else '1'
                tw = d.textlength(txt, font=f_k)
                d.text((cx - tw / 2, cy - 13), txt, fill='white', font=f_k)
                marked.append(ref)
            else:
                d.rectangle(box, fill=(150, 150, 150) if hot else (215, 215, 215))
        cx, cy = px(f.GetPosition().x / 1e6, f.GetPosition().y / 1e6)
        if hot:
            tw = d.textlength(ref, font=f_ref)
            if cb.GetWidth() / 1e6 < 3:   # narrow part: label on the left
                lx = px(cb.GetX() / 1e6, 0)[0] - tw - 6
                d.text((lx, cy - 11), ref, fill=(160, 80, 0), font=f_ref)
            else:
                ty = px(0, cb.GetY() / 1e6)[1] - 22
                d.text((cx - tw / 2, ty), ref, fill=(160, 80, 0), font=f_ref)
        else:
            tw = d.textlength(ref, font=f_small)
            d.text((cx - tw / 2, cy - 8), ref, fill=(140, 140, 140), font=f_small)
    ly = H - 160
    d.text((M, ly), 'POLARITY CHECK - top view, same orientation as the JLCPCB preview', fill='black', font=f_title)
    d.rectangle([M, ly + 45, M + 28, ly + 73], fill=(220, 0, 0))
    d.text((M + 40, ly + 45), 'K = cathode pad: the band / line / chamfered end of the diode or LED must be on THIS side',
           fill='black', font=f_ref)
    d.rectangle([M, ly + 85, M + 28, ly + 113], fill=(0, 70, 220))
    d.text((M + 40, ly + 85), '1 = pin 1: the dot / notch / bevel of the IC or MOSFET must be at THIS pad',
           fill='black', font=f_ref)
    d.text((M, ly + 125), 'Checked by scripts/check_polarity.py: footprint = JLCPCB footprint, cathode net on the pin '
           'JLCPCB calls cathode, JLCPCB silk mark on that pin.', fill=(90, 90, 90), font=f_small)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    img.save(OUT)
    missing = (set(design.CATHODE) | PIN1) - set(marked)
    assert not missing, missing
    print('wrote', OUT, len(marked), 'parts marked')


if __name__ == '__main__':
    sys.exit(main())
