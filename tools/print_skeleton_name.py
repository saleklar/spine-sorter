import sys, json, re, os
p = sys.argv[1] if len(sys.argv) > 1 else None
if not p:
    print('Usage: print_skeleton_name.py <path/to/game_intro.json>')
    sys.exit(2)
try:
    with open(p, 'r', encoding='utf-8', errors='ignore') as fh:
        j = json.load(fh)
except Exception as e:
    print('ERROR reading JSON:', e)
    sys.exit(1)
print('--- skeleton block ---')
print(json.dumps(j.get('skeleton'), indent=2, ensure_ascii=False))
raw_name = None
s = j.get('skeleton')
if isinstance(s, dict):
    raw_name = s.get('name') or s.get('hash')
print('\nraw skeleton.name:', repr(raw_name))

def clean(bn):
    parts = bn.split('-')
    keep = []
    for part in parts:
        if re.match(r'^\d', part):
            break
        keep.append(part)
    return '-'.join(keep) if keep else bn

if raw_name:
    print('cleaned from skeleton.name:', clean(str(raw_name)))
else:
    bn = os.path.splitext(os.path.basename(p))[0]
    print('cleaned from filename:', clean(bn))
