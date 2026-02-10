import sys, json, os

if len(sys.argv) < 2:
    print('Usage: check_references.py <json>')
    sys.exit(2)

p = sys.argv[1]
if not os.path.exists(p):
    print('File not found', p); sys.exit(1)

with open(p, 'r', encoding='utf-8', errors='ignore') as fh:
    j = json.load(fh)

slots = set()
for s in j.get('slots', []):
    if isinstance(s, dict) and 'name' in s:
        slots.add(s['name'])

bones = set()
for b in j.get('bones', []):
    if isinstance(b, dict) and 'name' in b:
        bones.add(b['name'])

constraints = set()
for c in j.get('constraints', []):
    if isinstance(c, dict) and 'name' in c:
        constraints.add(c['name'])

missing = []
# skins attachments reference slots
skins = j.get('skins', {})
if isinstance(skins, dict):
    for skin_name, skin_val in skins.items():
        if isinstance(skin_val, dict):
            for slot_key in skin_val.keys():
                if slot_key not in slots:
                    missing.append(f"Skin '{skin_name}' references missing slot '{slot_key}'")

# animations
anims = j.get('animations', {})
if isinstance(anims, dict):
    for anim_name, anim_val in anims.items():
        if isinstance(anim_val, dict):
            slots_t = anim_val.get('slots', {})
            if isinstance(slots_t, dict):
                for sk in slots_t.keys():
                    if sk not in slots:
                        missing.append(f"Animation '{anim_name}' slots timeline references missing slot '{sk}'")
            bones_t = anim_val.get('bones', {})
            if isinstance(bones_t, dict):
                for bk in bones_t.keys():
                    if bk not in bones:
                        missing.append(f"Animation '{anim_name}' bones timeline references missing bone '{bk}'")
            cons_t = anim_val.get('constraints', {})
            if isinstance(cons_t, dict):
                for ck in cons_t.keys():
                    if ck not in constraints:
                        missing.append(f"Animation '{anim_name}' constraints timeline references missing constraint '{ck}'")

if missing:
    print('REFERENTIAL INTEGRITY ISSUES:')
    for m in missing:
        print('-', m)
    sys.exit(1)
else:
    print('All references OK')
    sys.exit(0)
