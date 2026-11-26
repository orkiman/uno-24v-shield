"""
Single source of truth for the UNO 24V shield v6 netlist.

Derived from EasyEDA project "uno glue controller single fet 231125"
(schematic "arduino uno 24v shield v5 2025-10-22") with these changes:
  * removed current sensing: INA8..INA11, RS8..RS11, R8..R11, C8-1..C11-1
  * removed glue-gun controller: Q5, L1, R15, R16(R17), +48V, D8-4/D8-5(/D8-6)
  * MOSFET sources go straight to GND (shunts removed)
  * flyback clamp return (old net THICK-LOAD+V) is the board +24V (after F1);
    J5 pin 3 (was "VL+") is now a second GND terminal (5A total return)
  * input protection: F1 resettable fuse + TVS5 SMBJ28A (surge clamp and
    reverse-polarity crowbar)
  * out-of-stock parts swapped for pin/footprint compatible parts

Each part: ref -> dict(old=v5 ref, sym=lib_id, value, fp=footprint name in
uno24v.pretty, lcsc, mpn, desc, pos=(x,y) on schematic, nets={pin: net}).
Pins not listed in `nets` are intentionally unconnected (no-connect flag).
"""

FP_LIB = 'uno24v'

PARTS = {}
# schematic only: pins joined by a direct wire instead of two net labels
LINKS = []


def part(ref, old, sym, value, fp, lcsc, mpn, desc, pos, nets, **kw):
    PARTS[ref] = dict(ref=ref, old=old, sym=sym, value=value, fp=fp, lcsc=lcsc,
                      mpn=mpn, desc=desc, pos=pos, nets=nets, **kw)


# ---------------------------------------------------------------- power
# 4P (same part as J6/J7): pin 1 on the v5 "24v" hole, pins 2,3 on the v5 holes,
# pin 4 is a new hole; three GND terminals share the 5 A load return current
part('J5', 'CN7', 'Connector_Generic:Conn_01x04', 'PWR 24V', 'CONN-TH_4P-P3.50_KF250-3.5-4P-1',
     'C475156', 'KF250-3.5-4P-1', '4P 3.5mm spring terminal: 1=+24V, 2,3,4=GND (5 A load return)',
     (40.64, 63.5), {1: '+24V_IN', 2: 'GND', 3: 'GND', 4: 'GND'})
part('F1', None, 'Device:Polyfuse', '1.1A 48V', 'F1812',
     'C19723490', '1812L110/48QR', 'Resettable fuse 1.1A hold / 2.2A trip, 48V, 1812',
     (0, 0), {1: '+24V', 2: '+24V_IN'})
part('TVS5', None, 'Device:D_Zener', 'SMBJ28A', 'SMB_L4.3-W3.6-LS5.4-RD',
     'C113997', 'SMBJ28A', 'Input TVS 28V: surge clamp, reverse-polarity crowbar with F1',
     (0, 0), {1: '+24V', 2: 'GND'})
part('D1', 'D1', 'Device:D_Schottky', 'DS210W', 'SOD-123FL_L2.7-W1.8-LS3.8-RD',
     'C116100', 'DS210W', 'Reverse polarity, 100V 2A Schottky SOD-123F',
     (81.28, 50.8), {1: 'VREG_IN', 2: '+24V_IN'})
part('U3', 'U3', 'uno24v:78M12', '78M12', 'TO-252-2_L6.6-W6.1-P4.57-LS9.9-TL-CW',
     'C116325', '78M12', '12V 0.5A linear regulator -> Arduino VIN',
     (116.84, 50.8), {1: 'VREG_IN', 2: 'GND', 3: 'ARD_VIN'})
part('R1', 'R13', 'Device:R', '200', 'R0603', 'C8218', '0603WAF2000T5E', '200R 1% 0603',
     (152.4, 50.8), {1: 'LED_5V', 2: '+5V'}, rot=180)
part('LED1', '5VLED', 'uno24v:LED_A1K2', 'BLUE 5V', 'LED0603-FD', 'C19171394', 'YLED0603B',
     '+5V indicator', (152.4, 71.12), {1: 'LED_5V', 2: 'GND'}, rot=90)
LINKS.append((('R1', 1), ('LED1', 1)))

# ---------------------------------------------------------------- arduino headers
part('J1', 'U1', 'Connector_Generic:Conn_01x08', 'ARD POWER', 'HDR-TH_8P-P2.54-H-M',
     'C358689', 'MTP125-1108S1', 'Arduino power header: NC IOREF RST 3V3 5V GND GND VIN',
     (40.64, 111.76), {3: 'RESET', 5: '+5V', 6: 'GND', 7: 'GND', 8: 'ARD_VIN'})
part('J4', 'H1', 'Connector_Generic:Conn_01x06', 'ARD A0-A5', 'HDR-TH_6P-P2.54-V-M-1',
     'C178289', '68000-406HLF', 'Arduino analog header A0..A5 (mechanical only)',
     (40.64, 147.32), {})
part('J2', 'H2', 'Connector_Generic:Conn_01x10', 'ARD D8-SCL', 'HDR-TH_10P-P2.54-V-M-1',
     'C57369', 'Headers Pins2.54mm1*10P', 'Arduino header: SCL SDA AREF GND D13 D12 D11 D10 D9 D8',
     (40.64, 185.42), {7: 'D11', 8: 'D10', 9: 'D9', 10: 'D8'})
part('J3', 'U7', 'Connector_Generic:Conn_01x08', 'ARD D7-D0', 'HDR-TH_8P-P2.54-H-M',
     'C358689', 'MTP125-1108S1', 'Arduino header: D7 D6 D5 D4 D3 D2 D1 D0',
     (40.64, 228.6), {3: 'D5', 4: 'D4', 5: 'D3', 6: 'D2', 7: 'D1_TX', 8: 'D0_RX'})
part('SW1', 'SW1', 'Switch:SW_Push', 'RESET', 'SW-SMD_L4.0-W2.9-LS5.0',
     'C720477', 'TS-1088-AR02016', 'Reset push button', (81.28, 106.68), {1: 'GND', 2: 'RESET'})

# ---------------------------------------------------------------- outputs D8..D11
part('RN3', 'R14', 'Device:R_Pack04_Split', '220', 'RES-ARRAY-SMD_0402-8P-L2.0-W1.0-BL',
     'C728719', 'YC124-FR-07220RL', 'Gate resistors 4x220R 0402x4',
     (180.34, 60.96), {1: 'Q4_G', 2: 'Q3_G', 3: 'Q2_G', 4: 'Q1_G', 5: 'D8', 6: 'D9', 7: 'D10', 8: 'D11'})
part('RN6', 'RN6', 'Device:R_Pack04_Split', '100k', 'RES-ARRAY-SMD_0402-8P-L2.0-W1.0-BL',
     'C25724', '4D02WGJ0104TCE', 'Gate pull-downs 4x100k 0402x4',
     (180.34, 99.06), {1: 'D11', 2: 'D10', 3: 'D9', 4: 'D8', 5: 'GND', 6: 'GND', 7: 'GND', 8: 'GND'})
part('RN5', 'RN5', 'Device:R_Pack04_Split', '330', 'RES-ARRAY-SMD_0402-8P-L2.0-W1.0-BL',
     'C170189', 'WA04X331JTL', 'Output LED resistors 4x330R 0402x4',
     (180.34, 137.16), {1: 'LED2_A', 2: 'LED3_A', 3: 'LED4_A', 4: 'LED5_A', 5: 'D11', 6: 'D10', 7: 'D9', 8: 'D8'})
for i, (ch, old) in enumerate([('D8', 'O8'), ('D9', 'O9'), ('D10', 'O10'), ('D11', 'O11')]):
    part('LED%d' % (i + 2), old, 'uno24v:LED_A1K2', 'RED ' + ch, 'LED0603-FD', 'C19171390', 'YLED0603R',
         'Output %s indicator (above terminal "%s")' % (ch, ch[1:]),
         (210.82 + 15.24 * i, 162.56), {1: 'LED%d_A' % (i + 2), 2: 'GND'}, rot=90)

# per-channel power stage: Q, flyback Schottky DF, flyback clamp zener DZ, D-S TVS
CH = [  # (n, arduino pin, Q, terminal pin, v5 refs D?-1 zener, D?-2 schottky, D?-3 tvs)
    (1, 'D8', 'Q1', 4, 'D8'),
    (2, 'D9', 'Q2', 3, 'D9'),
    (3, 'D10', 'Q3', 2, 'D10'),
    (4, 'D11', 'Q4', 1, 'D11'),
]
for n, pin, q, tp, oldp in CH:
    x0 = 228.6 + (n - 1) * 45.72
    out = 'OUT_' + pin
    fb = 'FB_' + pin
    part(q, q, 'uno24v:BSC0805LS', 'BSC0805LS', 'PG-TDSON-8_L5.2-W5.9-P1.27-LS6.2-BL-EP',
         'C534374', 'BSC0805LS', 'N-MOSFET 100V 7mR logic level, output %s' % pin,
         (x0, 76.2), {1: 'GND', 2: 'GND', 3: 'GND', 4: '%s_G' % q, 5: out, 6: out, 7: out, 8: out, 9: out})
    part('DF%d' % n, oldp + '-2', 'Device:D_Schottky', 'SS56B', 'SMB_L4.6-W3.7-LS5.4-RD',
         'C5343335', 'SS56B', 'Flyback Schottky 60V 5A, output %s' % pin,
         (x0 + 20.32, 58.42), {1: fb, 2: out}, rot=270)
    part('DZ%d' % n, oldp + '-1', 'Device:D_Zener', 'SMBJ15A', 'SMB_L4.6-W3.6-LS5.3-RD',
         'C908796', 'SMBJ15A', 'Flyback clamp TVS 15V (fast decay), output %s' % pin,
         (x0 + 20.32, 33.02), {1: fb, 2: '+24V'}, rot=90)
    part('TVS%d' % n, oldp + '-3', 'uno24v:D_TVS_A1K2', 'SMBJ58A', 'SMB_L4.6-W3.6-LS5.3-R-RD',
         'C41376102', 'SMBJ58A', 'Drain-source TVS 58V, output %s' % pin,
         (x0 + 20.32, 88.9), {1: 'GND', 2: out}, rot=270)
    LINKS.append((('DZ%d' % n, 1), ('DF%d' % n, 1)))
    LINKS.append((('DF%d' % n, 2), ('TVS%d' % n, 2)))
part('J6', 'CN6', 'Connector_Generic:Conn_01x04', 'OUTPUTS', 'CONN-TH_4P-P3.50_KF250-3.5-4P-1',
     'C475156', 'KF250-3.5-4P-1', 'Outputs (low side): 1=D11 2=D10 3=D9 4=D8',
     (403.86, 116.84), {1: 'OUT_D11', 2: 'OUT_D10', 3: 'OUT_D9', 4: 'OUT_D8'})

# ---------------------------------------------------------------- inputs D2..D5
part('J7', 'CN5', 'Connector_Generic:Conn_01x04', 'INPUTS', 'CONN-TH_4P-P3.50_KF250-3.5-4P-1',
     'C475156', 'KF250-3.5-4P-1', 'Inputs 24V: 1=D5 2=D4 3=D3 4=D2',
     (190.5, 213.36), {1: 'IN_D5', 2: 'IN_D4', 3: 'IN_D3', 4: 'IN_D2'})
part('RN1', 'RN1', 'Device:R_Pack04_Split', '10k', 'RES-ARRAY-SMD_0603-8P-L3.2-W1.6-BL',
     'C107374', 'YC164-JR-0710KL', 'Input resistors 4x10k 0603x4',
     (223.52, 195.58), {1: 'ULN_I4', 2: 'ULN_I3', 3: 'ULN_I2', 4: 'ULN_I1', 5: 'IN_D2', 6: 'IN_D2', 7: 'IN_D3', 8: 'IN_D3'})
part('RN4', 'RN4', 'Device:R_Pack04_Split', '10k', 'RES-ARRAY-SMD_0603-8P-L3.2-W1.6-BL',
     'C107374', 'YC164-JR-0710KL', 'Input resistors 4x10k 0603x4',
     (223.52, 238.76), {1: 'ULN_I8', 2: 'ULN_I7', 3: 'ULN_I6', 4: 'ULN_I5', 5: 'IN_D4', 6: 'IN_D4', 7: 'IN_D5', 8: 'IN_D5'})
part('U4', 'U4', 'Transistor_Array:ULN2803A', 'ULN2803A', 'SOP-18_L11.4-W7.6-P1.27-LS10.6-BL',
     'C845537', 'ULN2803A', 'Darlington array: input level shift + LED drive',
     (269.24, 213.36), {1: 'ULN_I1', 2: 'ULN_I2', 3: 'ULN_I3', 4: 'ULN_I4', 5: 'ULN_I5', 6: 'ULN_I6',
                        7: 'ULN_I7', 8: 'ULN_I8', 9: 'GND',
                        18: 'D2', 17: 'LED6_K', 16: 'D3', 15: 'LED7_K', 14: 'D4', 13: 'LED8_K', 12: 'D5', 11: 'LED9_K'})
part('RN2', 'RN2', 'Device:R_Pack04_Split', '220', 'RES-ARRAY-SMD_0603-8P-L3.2-W1.6-BL',
     'C29719', '4D03WGJ0221T5E', 'Input LED resistors 4x220R 0603x4',
     (314.96, 195.58), {1: 'LED6_A', 2: 'LED7_A', 3: 'LED8_A', 4: 'LED9_A', 5: '+5V', 6: '+5V', 7: '+5V', 8: '+5V'})
for i in range(4):
    part('LED%d' % (6 + i), 'I%d' % (2 + i), 'uno24v:LED_A1K2', 'GREEN D%d' % (2 + i),
         'LED-SMD_L1.6-W0.8_19-219-GHC-YR2T1B5Y-3T', 'C2994781', '19-219/GHC-YR2T1B5Y/3T',
         'Input D%d indicator' % (2 + i), (302.26 + 12.7 * i, 228.6),
         {1: 'LED%d_A' % (6 + i), 2: 'LED%d_K' % (6 + i)}, rot=270)

# ---------------------------------------------------------------- RS232
part('U2', 'U2', 'Interface_UART:MAX232', 'MAX232ESE', 'SOIC-16_L9.9-W3.9-P1.27-LS6.0-BL',
     'C26860', 'MAX232ESE+T', 'RS232 transceiver', (93.98, 236.22),
     {1: 'C1P', 2: 'VPOS', 3: 'C1N', 4: 'C2P', 5: 'C2N', 6: 'VNEG', 11: 'D1_TX', 12: 'RX_232',
      13: 'RS232_RX', 14: 'RS232_TX', 15: 'GND', 16: '+5V'})
part('C1', 'C1', 'Device:C', '1uF', 'C0603', 'C1592', 'CL10A105KO8NNNC', '1uF 16V X5R 0603',
     (63.5, 254.0), {1: 'C1N', 2: 'C1P'})
part('C2', 'C2', 'Device:C', '1uF', 'C0603', 'C1592', 'CL10A105KO8NNNC', '1uF 16V X5R 0603',
     (127.0, 208.28), {1: 'C2N', 2: 'C2P'})
part('C3', 'C3', 'Device:C', '1uF', 'C0603', 'C1592', 'CL10A105KO8NNNC', '1uF 16V X5R 0603',
     (139.7, 233.68), {1: 'GND', 2: 'VNEG'})
part('C4', 'C4', 'Device:C', '1uF', 'C0603', 'C1592', 'CL10A105KO8NNNC', '1uF 16V X5R 0603',
     (152.4, 208.28), {1: 'VPOS', 2: '+5V'})
part('J8', 'DSUB1', 'uno24v:DB9_Female_MH', 'RS232 DB9F', 'DSUB-TH_DS1034-01-09FBN044',
     'C53474757', 'DS1034-01-09FBN044-JC', 'DB9 female (same connector as v5): 2=TX out 3=RX in 5=GND',
     (167.64, 266.7), {2: 'RS232_TX', 3: 'RS232_RX', 5: 'GND'})
part('JP1', 'RXJ', 'Connector_Generic:Conn_01x02', 'RX JUMPER', 'HDR-TH_2P-P2.54-V-M-1',
     'C234182', '22-28-4020', 'Remove jumper to free D0 while uploading sketch',
     (50.8, 274.32), {1: 'D0_RX', 2: 'RX_232'})

# nets that carry load current -> PCB net class "Power"
POWER_NETS = ['+24V_IN', '+24V', 'GND', 'OUT_D8', 'OUT_D9', 'OUT_D10', 'OUT_D11',
              'FB_D8', 'FB_D9', 'FB_D10', 'FB_D11']

# nets drawn with power symbols in the schematic
POWER_SYMBOL_NETS = {'GND': 'power:GND', '+5V': 'power:+5V', '+24V': 'power:+24V'}
# nets that need a PWR_FLAG (driven only through connectors / passive parts)
PWR_FLAG_NETS = ['GND', '+5V', '+24V', 'VREG_IN']

# v5 PCB net name -> v6 net name (used to re-net the existing copper)
OLD_NET_MAP = {
    '$1N25': '+24V_IN', 'THICK-LOAD+V': '+24V', '$1N5': 'VREG_IN', '$1N20': 'ARD_VIN',
    '+5V': '+5V', 'GND': 'GND', '$1N596': 'LED_5V', '$1N19': 'RESET',
    '$1N19956': 'D8', '$1N19936': 'D9', '$1N19946': 'D10', '$1N19926': 'D11',
    '$1N20048': 'Q1_G', '$1N20053': 'Q2_G', '$1N19892': 'Q3_G', '$1N20058': 'Q4_G',
    'TH7': 'OUT_D8', 'TH5': 'OUT_D9', 'TH3': 'OUT_D10', 'TH1': 'OUT_D11',
    'TH8': 'GND', 'TH6': 'GND', 'TH4': 'GND', 'TH2': 'GND',
    'TH9': 'FB_D8', 'TH10': 'FB_D9', 'TH11': 'FB_D10', 'TH12': 'FB_D11',
    '$1N2481': 'LED2_A', '$1N2485': 'LED3_A', '$1N2489': 'LED4_A', '$1N2499': 'LED5_A',
    '$1N4108': 'IN_D2', '$1N49': 'IN_D3', '$1N50': 'IN_D4', '$1N51': 'IN_D5',
    '$1N599': 'ULN_I1', '$1N600': 'ULN_I2', '$1N601': 'ULN_I3', '$1N602': 'ULN_I4',
    '$1N55': 'ULN_I5', '$1N54': 'ULN_I6', '$1N53': 'ULN_I7', '$1N52': 'ULN_I8',
    '$1N26': 'D2', '$1N27': 'D3', '$1N28': 'D4', '$1N29': 'D5',
    '$1N30': 'LED6_K', '$1N31': 'LED7_K', '$1N32': 'LED8_K', '$1N33': 'LED9_K',
    '$1N8074': 'LED6_A', '$1N8085': 'LED7_A', '$1N8105': 'LED8_A', '$1N8110': 'LED9_A',
    '$1N21': 'C1P', '$1N7': 'C1N', '$1N13': 'C2P', '$1N8': 'C2N', '$1N10': 'VNEG', '$1N14': 'VPOS',
    '$1N6': 'D1_TX', '$1N56': 'RX_232', '$1N57': 'D0_RX', '$1N12': 'RS232_TX', '$1N11': 'RS232_RX',
    # removed current-sense circuitry
    '$1N10348': None, '$1N19778': None, '$1N19775': None, '$1N19766': None,
    '$1N10353': None, '$1N10722': None, '$1N10973': None, '$1N11224': None, '$1N16140': None,
}

REMOVED_V5_REFS = ['INA8', 'INA9', 'INA10', 'INA11', 'RS8', 'RS9', 'RS10', 'RS11',
                   'R8', 'R9', 'R10', 'R11', 'C8-1', 'C9-1', 'C10-1', 'C11-1']


# parts whose footprint is taken directly from the LCSC/JLCPCB library
LCSC_FOOTPRINTS = {'D1': 'C116100', 'TVS5': 'C113997'}

# intended cathode net of every polarized 2-pin part (checked against the
# LCSC/JLCPCB pin names by scripts/check_polarity.py)
CATHODE = {'D1': 'VREG_IN', 'TVS5': '+24V', 'LED1': 'GND'}
for _n, _ch in ((1, 'D8'), (2, 'D9'), (3, 'D10'), (4, 'D11')):
    CATHODE['DF%d' % _n] = 'FB_' + _ch
    CATHODE['DZ%d' % _n] = 'FB_' + _ch
    CATHODE['TVS%d' % _n] = 'OUT_' + _ch
for _k in range(2, 6):
    CATHODE['LED%d' % _k] = 'GND'
for _k in range(6, 10):
    CATHODE['LED%d' % _k] = 'LED%d_K' % _k
for _r, _c in CATHODE.items():
    PARTS[_r]['cathode'] = _c


def nets():
    """net -> list of (ref, pin)"""
    out = {}
    for r, p in PARTS.items():
        for pin, n in p['nets'].items():
            out.setdefault(n, []).append((r, str(pin)))
    return out
