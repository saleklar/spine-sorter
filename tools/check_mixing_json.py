import json, os, sys

path = r"Z:\spine sorter v257\test_files_from_collegues\me\symbols.json"
print(f"Loading: {path}")
if not os.path.exists(path):
    print("ERROR: file not found")
    sys.exit(2)

with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
    j = json.load(fh)

warnings = []
try:
    if not isinstance(j, dict):
        print('Invalid JSON root')
        sys.exit(1)
    anims = j.get('animations', {})
    if not isinstance(anims, dict) or len(anims) <= 1:
        print('No or single animation — no mixing risk detected by this check.')
        sys.exit(0)

    # Parse setup pose
    setup_slots = {}
    setup_bones = {}
    for s in j.get('slots', []) or []:
        if not isinstance(s, dict):
            continue
        name = s.get('name')
        if not name: continue
        setup_slots[name] = {'attachment': s.get('attachment'), 'color': s.get('color')}
    for b in j.get('bones', []) or []:
        if not isinstance(b, dict): continue
        name = b.get('name')
        if not name: continue
        setup_bones[name] = {
            'x': float(b.get('x', 0.0)),
            'y': float(b.get('y', 0.0)),
            'rotation': float(b.get('rotation', 0.0)) if b.get('rotation') is not None else 0.0,
            'scaleX': float(b.get('scaleX', 1.0)) if b.get('scaleX') is not None else 1.0,
            'scaleY': float(b.get('scaleY', 1.0)) if b.get('scaleY') is not None else 1.0,
        }

    slot_props = {}
    bone_props = {}
    for aname, aobj in anims.items():
        slot_props[aname] = {}
        bone_props[aname] = {}
        if not isinstance(aobj, dict):
            continue
        slots_node = aobj.get('slots')
        if isinstance(slots_node, dict):
            for sname, timelines in slots_node.items():
                if not isinstance(timelines, dict): continue
                slot_props[aname].setdefault(sname, {})
                att = timelines.get('attachment')
                if isinstance(att, list) and len(att) > 0:
                    setup_val = setup_slots.get(sname, {}).get('attachment')
                    changes = False
                    for k in att:
                        namev = k.get('name') or k.get('attachment') or None
                        if namev is None: continue
                        if namev != setup_val:
                            changes = True; break
                    slot_props[aname][sname]['attachment_changes'] = changes
                col = timelines.get('color')
                if isinstance(col, list) and len(col) > 0:
                    setup_val = setup_slots.get(sname, {}).get('color')
                    changes = False
                    for k in col:
                        c = k.get('color')
                        if c is None: continue
                        if setup_val is None or str(c).lower() != str(setup_val).lower():
                            changes = True; break
                    slot_props[aname][sname]['color_changes'] = changes
        bones_node = aobj.get('bones')
        if isinstance(bones_node, dict):
            for bname, timelines in bones_node.items():
                if not isinstance(timelines, dict): continue
                bone_props[aname].setdefault(bname, {})
                trans = timelines.get('translate')
                if isinstance(trans, list) and len(trans) > 0:
                    setup = setup_bones.get(bname, {})
                    changes = False
                    for k in trans:
                        x = float(k.get('x', setup.get('x', 0.0)))
                        y = float(k.get('y', setup.get('y', 0.0)))
                        if abs(x - setup.get('x', 0.0)) > 1e-6 or abs(y - setup.get('y', 0.0)) > 1e-6:
                            changes = True; break
                    bone_props[aname][bname]['translate_changes'] = changes
                rot = timelines.get('rotate')
                if isinstance(rot, list) and len(rot) > 0:
                    setup = setup_bones.get(bname, {})
                    changes = False
                    for k in rot:
                        r = float(k.get('angle', k.get('rotation', setup.get('rotation', 0.0))))
                        if abs(r - setup.get('rotation', 0.0)) > 1e-6:
                            changes = True; break
                    bone_props[aname][bname]['rotate_changes'] = changes
                scale = timelines.get('scale')
                if isinstance(scale, list) and len(scale) > 0:
                    setup = setup_bones.get(bname, {})
                    changes = False
                    for k in scale:
                        sx = float(k.get('x', setup.get('scaleX', 1.0)))
                        sy = float(k.get('y', setup.get('scaleY', 1.0)))
                        if abs(sx - setup.get('scaleX', 1.0)) > 1e-6 or abs(sy - setup.get('scaleY', 1.0)) > 1e-6:
                            changes = True; break
                    bone_props[aname][bname]['scale_changes'] = changes

    slot_change_map = {}
    slot_defined_map = {}
    for aname, slots in slot_props.items():
        for sname, props in slots.items():
            for pkey in ['attachment_changes','color_changes']:
                if pkey in props:
                    slot_change_map.setdefault((sname,pkey), set()).add(aname)
                    slot_defined_map.setdefault((sname,pkey), set()).add(aname)
    bone_change_map = {}
    bone_defined_map = {}
    for aname, bones in bone_props.items():
        for bname, props in bones.items():
            for pkey in ['translate_changes','rotate_changes','scale_changes']:
                if pkey in props:
                    bone_change_map.setdefault((bname,pkey), set()).add(aname)
                    bone_defined_map.setdefault((bname,pkey), set()).add(aname)

    total_anims = len(anims)
    all_anims = set(anims.keys())
    for (sprop, changers) in slot_change_map.items():
        slot, prop = sprop
        defined = slot_defined_map.get(sprop, set())
        missing = sorted(list(all_anims - defined))
        if changers and missing:
            chlist = sorted(list(changers))
            for miss in missing:
                warnings.append(f"Animation '{miss}' does not define slot '{slot}' property ({prop.replace('_changes','')}) while other animations ({', '.join(chlist[:5])}{'...' if len(chlist)>5 else ''}) modify it away from the setup pose.")
    for (bprop, changers) in bone_change_map.items():
        bone, prop = bprop
        defined = bone_defined_map.get(bprop, set())
        missing = sorted(list(all_anims - defined))
        if changers and missing:
            chlist = sorted(list(changers))
            for miss in missing:
                warnings.append(f"Animation '{miss}' does not define bone '{bone}' property ({prop.replace('_changes','')}) while other animations ({', '.join(chlist[:5])}{'...' if len(chlist)>5 else ''}) modify it away from the setup pose.")

except Exception as e:
    warnings.append(f"Detection failed: {e}")

if not warnings:
    print('No mixing warnings detected.')
else:
    print('Mixing warnings:')
    for w in warnings:
        print(' -', w)

sys.exit(0)
