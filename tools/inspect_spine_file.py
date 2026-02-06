import zipfile, json, os, sys, re

path = r"Z:\spine sorter v257\test_files_from_collegues\me\original\symbols_v2.spine"

print(f"Inspecting: {path}")
if not os.path.exists(path):
    print("ERROR: file not found")
    sys.exit(2)

try:
    if zipfile.is_zipfile(path):
        print("Type: ZIP archive")
        with zipfile.ZipFile(path, 'r') as z:
            names = z.namelist()
            print(f"ZIP entries: {len(names)}")
            jsons = [n for n in names if n.lower().endswith('.json')]
            if not jsons:
                print("No JSON files found inside ZIP.")
                sys.exit(0)
            # prefer top-level jsons
            jsons_sorted = sorted(jsons)
            jname = jsons_sorted[0]
            print(f"Using JSON: {jname}")
            with z.open(jname) as jf:
                data = json.load(jf)
    else:
        print("Type: Binary (not a ZIP). Searching for embedded JSON...")
        # Try to locate a JSON blob by searching for b"\n{\"skeleton\"" or b"\"animations\"'
        with open(path, 'rb') as f:
            b = f.read()
        # try to find the first occurrence of b'{"skeleton' or b'"animations"'
        idx = b.find(b'{"skeleton')
        if idx == -1:
            idx = b.find(b'"animations"')
            if idx != -1:
                # back up to the nearest '{'
                idx = b.rfind(b'{', 0, idx)
        if idx == -1:
            print('Could not locate JSON start in binary file.')
            sys.exit(0)
        # crude brace matching
        start = idx
        depth = 0
        end = None
        for i in range(start, len(b)):
            ch = b[i:i+1]
            if ch == b'{':
                depth += 1
            elif ch == b'}':
                depth -= 1
                if depth == 0:
                    end = i+1
                    break
        if end is None:
            print('Could not extract complete JSON from binary file.')
            sys.exit(0)
        js = b[start:end].decode('utf-8', errors='replace')
        try:
            data = json.loads(js)
        except Exception as e:
            # fallback: try to find any top-level json by regex
            m = re.search(rb"\{[\s\S]{0,200000}\}\n?", b[start:start+200000])
            if not m:
                print('JSON parse failed:', e)
                sys.exit(0)
            js = m.group(0).decode('utf-8', errors='replace')
            data = json.loads(js)

    # Now summarize
    def safe_get(d, k, default=None):
        return d.get(k, default) if isinstance(d, dict) else default

    anims = safe_get(data, 'animations', {}) or {}
    bones = safe_get(data, 'bones', []) or []
    slots = safe_get(data, 'slots', []) or []
    skins = safe_get(data, 'skins', {}) or {}

    print(f"Animations: {len(anims)}")
    if isinstance(anims, dict):
        names = list(anims.keys())
        print("Animation names (first 20):", ", ".join(names[:20]))
    print(f"Bones: {len(bones)}, Slots: {len(slots)}")

    # Quick check: which slots or bones appear in some animations but not others
    def collect_prop_owners():
        slot_owners = {}
        bone_owners = {}
        if isinstance(anims, dict):
            for aname, aobj in anims.items():
                if not isinstance(aobj, dict):
                    continue
                s_node = aobj.get('slots') or {}
                if isinstance(s_node, dict):
                    for sname, timelines in s_node.items():
                        slot_owners.setdefault(sname, set()).add(aname)
                b_node = aobj.get('bones') or {}
                if isinstance(b_node, dict):
                    for bname, timelines in b_node.items():
                        bone_owners.setdefault(bname, set()).add(aname)
        return slot_owners, bone_owners

    slot_owners, bone_owners = collect_prop_owners()
    # report slots/bones used by less than total animations
    total_anims = len(anims) if isinstance(anims, dict) else 0
    def report_rare(mapping, label):
        rare = {k: v for k,v in mapping.items() if len(v) < total_anims}
        print(f"{label} that are not defined in every animation: {len(rare)}")
        for k,v in list(rare.items())[:30]:
            print(f" - {k}: used in {len(v)}/{total_anims} animations (examples: {', '.join(list(v)[:5])})")

    if total_anims > 0:
        report_rare(slot_owners, 'Slots')
        report_rare(bone_owners, 'Bones')

    print('Done.')

except Exception as e:
    print('ERROR during inspection:', e)
    sys.exit(1)
