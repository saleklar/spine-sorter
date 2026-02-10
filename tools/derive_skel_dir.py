import sys, os, json, re, math
p = sys.argv[1] if len(sys.argv)>1 else None
input_path = sys.argv[2] if len(sys.argv)>2 else None
if not p or not os.path.exists(p):
    print('Provide path to JSON')
    sys.exit(2)
internal_skeleton_name = os.path.splitext(os.path.basename(p))[0]
skeleton_name = os.path.splitext(os.path.basename(input_path))[0] if input_path else None
j_name = None
try:
    with open(p,'r',encoding='utf-8',errors='ignore') as fh:
        jtmp = json.load(fh)
        skel = jtmp.get('skeleton') if isinstance(jtmp.get('skeleton'), dict) else None
        if skel:
            j_name = skel.get('name') or skel.get('hash')
except Exception:
    j_name = None
# load optional mapping
name_map = {}
for _mp in [os.path.join(os.getcwd(),'skeleton_name_map.json'), os.path.join(os.getcwd(),'tools','skeleton_name_map.json')]:
    if os.path.isfile(_mp):
        try:
            with open(_mp,'r',encoding='utf-8') as _mf:
                _m = json.load(_mf)
                if isinstance(_m, dict):
                    name_map = _m
                    break
        except Exception:
            pass

# keep original j_name for mapping lookup before entropy-based discard
orig_j = j_name
# load optional mapping
name_map = {}
for _mp in [os.path.join(os.getcwd(),'skeleton_name_map.json'), os.path.join(os.getcwd(),'tools','skeleton_name_map.json')]:
    if os.path.isfile(_mp):
        try:
            with open(_mp,'r',encoding='utf-8') as _mf:
                _m = json.load(_mf)
                if isinstance(_m, dict):
                    name_map = _m
                    break
        except Exception:
            pass
# entropy check
if isinstance(j_name,str) and re.match(r'^[A-Za-z0-9]{6,20}$', j_name):
    try:
        counts={}
        for ch in j_name:
            counts[ch]=counts.get(ch,0)+1
        L=len(j_name)
        entropy=0.0
        for c in counts.values():
            p=c/L
            entropy -= p*math.log2(p)
        if entropy>=3.2:
            print('Detected high-entropy j_name:', j_name, 'entropy=',round(entropy,3))
            j_name=None
        else:
            print('Low-entropy j_name:', j_name, 'entropy=',round(entropy,3))
    except Exception as e:
        pass
# mapping override (check original j_name before any entropy discard)
if isinstance(orig_j,str) and orig_j in name_map:
    final_candidate = name_map[orig_j]
elif isinstance(internal_skeleton_name,str) and internal_skeleton_name in name_map:
    final_candidate = name_map[internal_skeleton_name]
elif isinstance(skeleton_name,str) and skeleton_name in name_map:
    final_candidate = name_map[skeleton_name]
else:
    final_candidate = j_name or internal_skeleton_name or skeleton_name or 'skeleton'
# clean function
def _clean_skel_name_inline(n):
    if not n:
        return '?'
    bn = os.path.splitext(os.path.basename(n))[0]
    parts = bn.split('-')
    keep=[]
    for p in parts:
        if re.match(r'^\d', p):
            break
        keep.append(p)
    res = '-'.join(keep) if keep else bn
    return res
print('internal_skeleton_name=',internal_skeleton_name)
print('j_name=',j_name)
print('final_candidate=',final_candidate)
print('final_skeleton_dir=',_clean_skel_name_inline(final_candidate))
