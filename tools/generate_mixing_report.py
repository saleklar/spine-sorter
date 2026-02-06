import argparse
import json
import csv
import os


def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def gather_setup(j):
    slot_defaults = {}
    for s in j.get('slots', []) or []:
        slot_defaults[s.get('name')] = {
            'attachment': s.get('attachment'),
            'color': s.get('color')
        }
    bone_defaults = {}
    for b in j.get('bones', []) or []:
        bone_defaults[b.get('name')] = {
            'x': float(b.get('x', 0)),
            'y': float(b.get('y', 0)),
            'rotation': float(b.get('rotation', 0)),
            'scaleX': float(b.get('scaleX', 1)),
            'scaleY': float(b.get('scaleY', 1)),
        }
    return slot_defaults, bone_defaults


def analyze(j, eps=1e-6):
    slot_defaults, bone_defaults = gather_setup(j)
    animations = j.get('animations', {}) or {}
    all_anim_names = list(animations.keys())

    # Records
    # bone_prop_modifiers[(bone,prop)] = set(anims that change away from setup)
    # bone_prop_definers[(bone,prop)] = set(anims that define timeline for that prop)
    bone_prop_modifiers = {}
    bone_prop_definers = {}

    # slot_prop_modifiers/definers for 'attachment' and 'color'
    slot_prop_modifiers = {}
    slot_prop_definers = {}

    for aname, anim in animations.items():
        bones = anim.get('bones', {}) or {}
        for bone_name, timelines in bones.items():
            for ttype, frames in timelines.items():
                prop = None
                changed = False
                if ttype == 'translate':
                    prop = 'translate'
                    # frames can be list of frames or dict keyed by time
                    # take first frame value if possible
                    if isinstance(frames, list) and frames:
                        f0 = frames[0]
                        dx = float(f0.get('x', 0)) - bone_defaults.get(bone_name, {}).get('x', 0)
                        dy = float(f0.get('y', 0)) - bone_defaults.get(bone_name, {}).get('y', 0)
                        if abs(dx) > eps or abs(dy) > eps:
                            changed = True
                elif ttype == 'rotate':
                    prop = 'rotation'
                    if isinstance(frames, list) and frames:
                        f0 = frames[0]
                        dr = float(f0.get('angle', f0.get('rotation', 0))) - bone_defaults.get(bone_name, {}).get('rotation', 0)
                        if abs(dr) > eps:
                            changed = True
                elif ttype == 'scale':
                    prop = 'scale'
                    if isinstance(frames, list) and frames:
                        f0 = frames[0]
                        sx = float(f0.get('x', f0.get('scaleX', 1))) - bone_defaults.get(bone_name, {}).get('scaleX', 1)
                        sy = float(f0.get('y', f0.get('scaleY', 1))) - bone_defaults.get(bone_name, {}).get('scaleY', 1)
                        if abs(sx) > eps or abs(sy) > eps:
                            changed = True
                else:
                    # other timeline types considered as definers but not necessarily numeric compare
                    prop = ttype
                    changed = True

                key = (bone_name, prop)
                bone_prop_definers.setdefault(key, set()).add(aname)
                if changed:
                    bone_prop_modifiers.setdefault(key, set()).add(aname)

        slots = anim.get('slots', {}) or {}
        for slot_name, timelines in slots.items():
            for ttype, frames in timelines.items():
                if ttype == 'attachment':
                    slot_prop_definers.setdefault((slot_name, 'attachment'), set()).add(aname)
                    # check if attachment differs from default
                    if isinstance(frames, list) and frames:
                        f0 = frames[0]
                        att = f0.get('name') or f0.get('attachment')
                        default = slot_defaults.get(slot_name, {}).get('attachment')
                        if att != default:
                            slot_prop_modifiers.setdefault((slot_name, 'attachment'), set()).add(aname)
                elif ttype == 'color':
                    slot_prop_definers.setdefault((slot_name, 'color'), set()).add(aname)
                    if isinstance(frames, list) and frames:
                        f0 = frames[0]
                        col = f0.get('color')
                        default = slot_defaults.get(slot_name, {}).get('color')
                        if col and col != default:
                            slot_prop_modifiers.setdefault((slot_name, 'color'), set()).add(aname)
                else:
                    slot_prop_definers.setdefault((slot_name, ttype), set()).add(aname)
                    slot_prop_modifiers.setdefault((slot_name, ttype), set()).add(aname)

    # Build flagged rows
    rows = []
    def _shares_prefix_tokens(a, b, n=2):
        # return True if first n underscore-separated tokens match
        if not a or not b:
            return False
        ta = a.split('_')
        tb = b.split('_')
        if len(ta) < n or len(tb) < n:
            return False
        return all(ta[i] == tb[i] for i in range(n))

    def _candidate_anims_from_mods(mods):
        if not mods:
            return []
        mods = set(mods)
        candidates = set()
        for cand in all_anim_names:
            for m in mods:
                if _shares_prefix_tokens(cand, m, 2):
                    candidates.add(cand)
                    break
        # If no candidates found with 2-token rule, try 1-token to be lenient
        if not candidates:
            for cand in all_anim_names:
                for m in mods:
                    if _shares_prefix_tokens(cand, m, 1):
                        candidates.add(cand)
                        break
        # Always include modifiers themselves
        candidates.update(mods)
        return sorted(candidates)

    for bone_prop, modifiers in bone_prop_modifiers.items():
        definers = bone_prop_definers.get(bone_prop, set())
        bone_name, prop = bone_prop
        candidate_anims = _candidate_anims_from_mods(modifiers)

        for aname in candidate_anims:
            if aname not in definers and len(modifiers - {aname}) > 0:
                rows.append({
                    'animation': aname,
                    'type': 'bone',
                    'target': bone_name,
                    'property': prop,
                    'modifiers': ';'.join(sorted(modifiers))
                })

    for slot_prop, modifiers in slot_prop_modifiers.items():
        definers = slot_prop_definers.get(slot_prop, set())
        slot_name, prop = slot_prop
        candidate_anims = _candidate_anims_from_mods(modifiers)

        for aname in candidate_anims:
            if aname not in definers and len(modifiers - {aname}) > 0:
                rows.append({
                    'animation': aname,
                    'type': 'slot',
                    'target': slot_name,
                    'property': prop,
                    'modifiers': ';'.join(sorted(modifiers))
                })

    return rows


def write_csv(rows, outpath):
    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    with open(outpath, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['animation', 'type', 'target', 'property', 'modifiers'])
        w.writeheader()
        for r in rows:
            w.writerow(r)


def write_summary(rows, outpath):
    # produce a simple text summary listing animations that need keys
    per_anim = {}
    for r in rows:
        an = r['animation']
        per_anim.setdefault(an, []).append(f"{r['type']}:{r['target']}({r['property']})")

    summary_path = os.path.splitext(outpath)[0] + '_summary.txt'
    with open(summary_path, 'w', encoding='utf-8') as f:
        if not per_anim:
            f.write('No animations require additional start keys.\n')
        else:
            f.write(f'Animations that require additional start keys: {len(per_anim)}\n')
            for an, items in sorted(per_anim.items()):
                f.write(f"- {an}: {len(items)} issues; examples: {', '.join(items[:5])}\n")

    # also return the per_anim map for printing
    return per_anim, summary_path


def write_asset_report(rows, outpath):
    # rows contain: animation,type,target,property,modifiers
    asset_map = {}
    for r in rows:
        key = (r['type'], r['target'], r['property'])
        asset_map.setdefault(key, {'modifiers': set(), 'defined': set()})
        asset_map[key]['modifiers'].update(r['modifiers'].split(';'))
        asset_map[key]['defined'].add(r['animation'])

    asset_rows = []
    all_anims = set()
    for r in rows:
        all_anims.add(r['animation'])
    # Note: all_anims here are animations that appeared in flagged rows; to be conservative
    # we will also accept a full set from the JSON caller if needed.

    for (typ, target, prop), info in sorted(asset_map.items()):
        modifiers = ';'.join(sorted(x for x in info['modifiers'] if x))
        defined = sorted(info['defined'])
        missing = sorted(list(all_anims - info['defined']))
        asset_rows.append({
            'type': typ,
            'target': target,
            'property': prop,
            'defined_in': ';'.join(defined),
            'missing_in': ';'.join(missing),
            'modifiers': modifiers,
        })

    asset_out = os.path.splitext(outpath)[0] + '_assets.csv'
    with open(asset_out, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['type', 'target', 'property', 'defined_in', 'missing_in', 'modifiers'])
        w.writeheader()
        for r in asset_rows:
            w.writerow(r)

    return asset_out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('json', help='Spine JSON file to analyze')
    p.add_argument('--out', default='tools/mixing_report.csv', help='CSV output path')
    args = p.parse_args()

    j = load_json(args.json)
    rows = analyze(j)
    write_csv(rows, args.out)
    per_anim, summary_path = write_summary(rows, args.out)
    print(f'Wrote {len(rows)} flagged rows to {args.out}')
    if not per_anim:
        print('No animations require additional start keys.')
    else:
        print(f"Animations that require keys: {len(per_anim)}")
        for an, items in sorted(per_anim.items()):
            print(f" - {an}: {len(items)} issues; examples: {', '.join(items[:5])}")
        print(f'Summary written to: {summary_path}')


if __name__ == '__main__':
    main()
