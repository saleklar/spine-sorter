import sys
import os
import json
import re


def sanitize_name(name: str) -> str:
    if not isinstance(name, str):
        return name
    s = name.strip().lower()
    s = re.sub(r'[^a-z0-9._\-]+', '_', s)
    s = re.sub(r'[_\-]{2,}', '_', s)
    s = s.strip('_-')
    if not s:
        return 'unnamed'
    return s


def unique_map_for(names):
    seen = {}
    out = {}
    for n in names:
        new = sanitize_name(n)
        if new in seen and seen[new] != n:
            # collision, append suffix
            i = 1
            candidate = f"{new}_fixed"
            while candidate in seen:
                i += 1
                candidate = f"{new}_fixed{i}"
            new = candidate
        seen[new] = n
        out[n] = new
    return out


def apply_autofix(j):
    modified = False
    # skeleton
    if isinstance(j.get('skeleton'), dict):
        skel = j['skeleton']
        for key in ('name', 'title', 'skeleton', 'spine'):
            if key in skel and isinstance(skel[key], str):
                new = sanitize_name(skel[key])
                if new != skel[key]:
                    skel[key] = new
                    modified = True

    # slots
    slot_map = {}
    if isinstance(j.get('slots'), list):
        names = [s.get('name') for s in j.get('slots') if isinstance(s, dict) and 'name' in s]
        slot_map = unique_map_for(names)
        for s in j.get('slots'):
            if isinstance(s, dict) and 'name' in s:
                orig = s['name']
                if orig in slot_map and slot_map[orig] != orig:
                    s['name'] = slot_map[orig]
                    modified = True

    # bones
    bone_map = {}
    if isinstance(j.get('bones'), list):
        names = [b.get('name') for b in j.get('bones') if isinstance(b, dict) and 'name' in b]
        bone_map = unique_map_for(names)
        for b in j.get('bones'):
            if isinstance(b, dict) and 'name' in b:
                orig = b['name']
                if orig in bone_map and bone_map[orig] != orig:
                    b['name'] = bone_map[orig]
                    modified = True

    # constraints
    constraint_map = {}
    if isinstance(j.get('constraints'), list):
        names = [c.get('name') for c in j.get('constraints') if isinstance(c, dict) and 'name' in c]
        constraint_map = unique_map_for(names)
        for c in j.get('constraints'):
            if isinstance(c, dict) and 'name' in c:
                orig = c['name']
                if orig in constraint_map and constraint_map[orig] != orig:
                    c['name'] = constraint_map[orig]
                    modified = True

    # skins: can be a dict (old format) or a list (exported format with name/attachments)
    skins_val = j.get('skins')
    if isinstance(skins_val, dict):
        new_skins = {}
        for skin_name, skin_val in skins_val.items():
            new_skin_name = sanitize_name(skin_name)
            if isinstance(skin_val, dict):
                new_skin_val = {}
                for slot_key, attachments in skin_val.items():
                    mapped_slot = slot_map.get(slot_key, sanitize_name(slot_key))
                    new_skin_val[mapped_slot] = attachments
                new_skins[new_skin_name] = new_skin_val
            else:
                new_skins[new_skin_name] = skin_val
            if new_skin_name != skin_name:
                modified = True
        j['skins'] = new_skins
    elif isinstance(skins_val, list):
        # exported JSON sometimes uses a list of skins: [{"name":..., "attachments": {...}}, ...]
        new_skin_list = []
        for skin in skins_val:
            if not isinstance(skin, dict):
                new_skin_list.append(skin)
                continue
            new_skin = dict(skin)
            # sanitize skin name
            if 'name' in skin and isinstance(skin['name'], str):
                new_name = sanitize_name(skin['name'])
                new_skin['name'] = new_name
                if new_name != skin['name']:
                    modified = True
            # remap attachments (slot keys)
            if 'attachments' in skin and isinstance(skin['attachments'], dict):
                new_attachments = {}
                for slot_key, attachments in skin['attachments'].items():
                    mapped_slot = slot_map.get(slot_key, sanitize_name(slot_key))
                    new_attachments[mapped_slot] = attachments
                new_skin['attachments'] = new_attachments
            new_skin_list.append(new_skin)
        j['skins'] = new_skin_list

    # animations: rename animation keys and propagate slot/bone/constraint renames within timelines
    if isinstance(j.get('animations'), dict):
        new_anims = {}
        for anim_name, anim_val in j.get('animations').items():
            new_anim_name = sanitize_name(anim_name)
            # avoid clobber
            if new_anim_name in new_anims and new_anim_name != anim_name:
                new_anim_name = new_anim_name + '_fixed'
            if isinstance(anim_val, dict):
                # slots timelines
                slots = anim_val.get('slots')
                if isinstance(slots, dict):
                    new_slots = {}
                    for slot_key, timelines in slots.items():
                        mapped = slot_map.get(slot_key, sanitize_name(slot_key))
                        new_slots[mapped] = timelines
                    anim_val['slots'] = new_slots
                # bones timelines
                bones = anim_val.get('bones')
                if isinstance(bones, dict):
                    new_bones = {}
                    for bone_key, timelines in bones.items():
                        mapped = bone_map.get(bone_key, sanitize_name(bone_key))
                        new_bones[mapped] = timelines
                    anim_val['bones'] = new_bones
                # constraints
                constraints = anim_val.get('constraints')
                if isinstance(constraints, dict):
                    new_cons = {}
                    for con_key, timelines in constraints.items():
                        mapped = constraint_map.get(con_key, sanitize_name(con_key))
                        new_cons[mapped] = timelines
                    anim_val['constraints'] = new_cons
            new_anims[new_anim_name] = anim_val
            if new_anim_name != anim_name:
                modified = True
        j['animations'] = new_anims

    return modified


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: apply_autofix_to_json.py <path_to_exported_json>')
        sys.exit(2)
    path = sys.argv[1]
    if not os.path.exists(path):
        print('File not found:', path)
        sys.exit(1)
    # create backups dir
    backup_dir = os.path.join(os.getcwd(), 'logs', 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    base = os.path.basename(path)
    bak_path = os.path.join(backup_dir, base + '.bak')
    # copy
    with open(path, 'rb') as fr, open(bak_path, 'wb') as fw:
        fw.write(fr.read())
    print('Backup written to', bak_path)
    # load
    with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
        j = json.load(fh)
    modified = apply_autofix(j)
    fixed_path = os.path.join(os.path.dirname(path), os.path.splitext(base)[0] + '_fixed.json')
    with open(fixed_path, 'w', encoding='utf-8') as fh:
        json.dump(j, fh, indent=2, ensure_ascii=False)
    print('Wrote fixed JSON to', fixed_path, 'modified=', modified)
    sys.exit(0)
