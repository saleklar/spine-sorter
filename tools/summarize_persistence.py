import csv
from pathlib import Path
p = Path(__file__).with_name('mixing_report_persistence.csv')
focus_anims = {'persistence_4_collect', 'persistence_4_tease'}
focus_targets = {('bone','rainbow_arch'), ('slot','rainbow_arch'), ('slot','rainbow_arch2')}
found = {a: [] for a in focus_anims}
if not p.exists():
    print('ERROR: report file not found at', p)
    raise SystemExit(1)
with p.open('r', encoding='utf-8', newline='') as f:
    r = csv.reader(f)
    hdr = next(r, None)
    for row in r:
        if len(row) < 5:
            continue
        anim, typ, tgt, prop, mods = row
        if anim in focus_anims and (typ, tgt) in focus_targets:
            found[anim].append((typ, tgt, prop, mods))
print('Focused mixing summary for persistence sample')
for a in sorted(focus_anims):
    print('\nAnimation:', a)
    if not found[a]:
        print('  - no missing keys for requested targets found')
    else:
        for typ, tgt, prop, mods in found[a]:
            print(f"  - missing: {typ} {tgt} ({prop}); modifiers: {mods}")
