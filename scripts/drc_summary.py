import json, sys, collections, subprocess
pcb = sys.argv[1]
out = sys.argv[2]
subprocess.run(['kicad-cli', 'pcb', 'drc', '--schematic-parity', '--severity-all', '--format', 'json', '-o', out, pcb], capture_output=True)
d = json.load(open(out))
print(collections.Counter((v['severity'], v['type']) for v in d['violations']))
print('unconnected', len(d['unconnected_items']), 'parity', len(d.get('schematic_parity', [])))
show = sys.argv[3].split(',') if len(sys.argv) > 3 else []
for v in d['violations']:
    if v['type'] in show:
        print(' ', v['type'], v['description'][:60], [i['description'] for i in v['items']], [(round(i['pos']['x'], 2), round(i['pos']['y'], 2)) for i in v['items']][:1])
for u in d['unconnected_items'][:40]:
    print('  UNC', [i['description'] for i in u['items']], [(round(i['pos']['x'], 2), round(i['pos']['y'], 2)) for i in u['items']])
for u in d.get('schematic_parity', [])[:40]:
    print('  PAR', u['description'], [i['description'] for i in u['items']])
