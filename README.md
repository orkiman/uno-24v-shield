# uno-24v-shield

Arduino UNO 24V I/O shield, KiCad 9 project (v6).

* Outputs D8–D11: low-side N-MOSFET per channel (BSC0805LS) with flyback (SS56B + SMBJ15A to +24V) and drain-source TVS (SMBJ58A).
* Inputs D2–D5: 24V inputs through ULN2803 with indicator LEDs.
* RS232 on D0/D1: MAX232 + DB9 female (JP1 = RX jumper).
* 24V → 78M12 → Arduino VIN.

| Path | Content |
|---|---|
| `hardware/` | KiCad project (schematic, PCB, project symbol + footprint libraries) |
| `fab/` | JLCPCB order package: gerber zip, BOM, CPL |
| `docs/` | Schematic PDF, PCB PDF, renders, ERC/DRC reports, **REVIEW.md** (change list and checks) |
| `scripts/` | Generators: `design.py` (netlist source of truth), `build_pcb.py`, `export_fab.py` |
| `source/easyeda/` | EasyEDA Pro backup of v5 that v6 is derived from |

Regenerate everything (KiCad 9 with its Python module required):

```
python3 scripts/build_pcb.py
python3 scripts/export_fab.py
```
