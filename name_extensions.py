"""Image file extensions inside Spine names.

A name like ``coin.png`` (bone, slot, skin, attachment, animation, event or constraint) or an attachment path like
``symbols/coin.png`` should never carry a file extension: Spine adds ``.png`` itself when it looks for images.
``strip_name_extensions`` removes ``.png .jpg .jpeg .webp .psd`` (any case, anywhere in the name) from a skeleton's
JSON data in place, and renames every reference to each renamed item so the skeleton stays intact.

Works with Spine 3.7 – 4.2 JSON (skins as a dict or a list, ``deform`` or ``attachments`` timelines).
"""
import re

_EXT_IN_NAME = re.compile(r"\.(?:png|jpe?g|webp|psd)(?![a-z0-9])", re.IGNORECASE)
_CONSTRAINT_KINDS = ("ik", "transform", "path", "physics")


def strip_ext(name):
    """``coin.png`` -> ``coin``, ``coin.PNG_glow`` -> ``coin_glow``; anything else unchanged."""
    return _EXT_IN_NAME.sub("", name) if isinstance(name, str) else name


def _skin_entries(j):
    """[(skin_name, slot_dict, skin_obj_or_None)] for list-style (4.x) and dict-style (3.x) skins."""
    skins = j.get("skins")
    out = []
    if isinstance(skins, list):
        for sk in skins:
            if isinstance(sk, dict):
                out.append((sk.get("name", "default"), sk.get("attachments") or {}, sk))
    elif isinstance(skins, dict):
        for name, slots in skins.items():
            out.append((name, slots if isinstance(slots, dict) else {}, None))
    return out


def strip_name_extensions(j, image_exists=None):
    """Edits the skeleton data ``j`` in place — never anything on disk. Returns a list of ``{'kind', 'old', 'new'}``;
    ``new`` is None when the name without its extension already exists (left unchanged so nothing merges by accident).

    ``image_exists(ref)`` (optional) tells whether an image for the extension-less reference ``ref`` (as Spine resolves
    it: images folder + ref + .png/.jpg) is really on disk. An attachment's image reference is only changed when it is;
    otherwise the reference is kept exactly as it was (a file really named "coin.png.png" keeps working)."""
    fixes = []

    def plan(kind, names):
        names = [n for n in names if isinstance(n, str) and n]
        taken, mapping = set(names), {}
        for n in names:
            c = strip_ext(n)
            if c == n:
                continue
            if not c or c in taken:
                fixes.append({"kind": kind, "old": n, "new": None})
                continue
            taken.add(c)
            mapping[n] = c
            fixes.append({"kind": kind, "old": n, "new": c})
        return mapping

    def ren(mapping, value):
        return mapping.get(value, value)

    def ren_keys(mapping, d):
        if not isinstance(d, dict) or not mapping:
            return d
        return {ren(mapping, k): v for k, v in d.items()}

    bones = [b for b in (j.get("bones") or []) if isinstance(b, dict)]
    slots = [s for s in (j.get("slots") or []) if isinstance(s, dict)]
    skins = _skin_entries(j)
    animations = j.get("animations") if isinstance(j.get("animations"), dict) else {}

    # ── plan every rename against the original names ──
    bone_map = plan("bone", [b.get("name") for b in bones])
    slot_map = plan("slot", [s.get("name") for s in slots])
    skin_map = plan("skin", [s[0] for s in skins])
    event_map = plan("event", list((j.get("events") or {}).keys()))
    anim_map = plan("animation", list(animations.keys()))
    con_maps = {k: plan(k + " constraint", [c.get("name") for c in (j.get(k) or []) if isinstance(c, dict)]) for k in _CONSTRAINT_KINDS}
    att_maps = {}                                    # slot (old name) -> {attachment old -> new}, shared by all skins
    for slot in {s for _, slot_dict, _ in skins for s in slot_dict}:
        names = sorted({a for _, slot_dict, _ in skins for a in (slot_dict.get(slot) or {})})
        m = plan("attachment in slot '%s'" % slot, names)
        if m:
            att_maps[slot] = m

    def att(slot_old, name):
        return ren(att_maps.get(slot_old, {}), name)

    # ── bones ──
    for b in bones:
        b["name"] = ren(bone_map, b.get("name"))
        if "parent" in b:
            b["parent"] = ren(bone_map, b["parent"])

    # ── slots (bone, setup attachment) ──
    for s in slots:
        old = s.get("name")
        if "attachment" in s:
            s["attachment"] = att(old, s["attachment"])
        s["name"] = ren(slot_map, old)
        if "bone" in s:
            s["bone"] = ren(bone_map, s["bone"])

    # ── constraints ──
    for kind in _CONSTRAINT_KINDS:
        for c in (j.get(kind) or []):
            if not isinstance(c, dict):
                continue
            c["name"] = ren(con_maps[kind], c.get("name"))
            if isinstance(c.get("bones"), list):
                c["bones"] = [ren(bone_map, x) for x in c["bones"]]
            if "bone" in c:
                c["bone"] = ren(bone_map, c["bone"])
            if "target" in c:                         # a path constraint targets a slot, the others a bone
                c["target"] = ren(slot_map if kind == "path" else bone_map, c["target"])

    # ── skins: names, bone/constraint lists, slot and attachment keys, attachment contents ──
    new_skins = {}
    for skin_name, slot_dict, skin_obj in skins:
        new_slots = {}
        for slot_old, atts in slot_dict.items():
            new_atts = {}
            for a_old, a in (atts or {}).items():
                a_new = att(slot_old, a_old)
                if isinstance(a, dict):
                    # the image Spine loads: "path" (3.x: "name"), else the attachment name itself
                    ref_key = "path" if isinstance(a.get("path"), str) else "name" if isinstance(a.get("name"), str) else None
                    ref_old = a[ref_key] if ref_key else a_old
                    ref_new = strip_ext(ref_old)
                    a_type = a.get("type") if isinstance(a.get("type"), str) else "region"
                    has_image = a_type in ("region", "mesh", "linkedmesh")
                    if not ref_key and a_new == a_old:
                        pass                                  # its name is its image and it could not be renamed (reported)
                    elif has_image and ref_new != ref_old:
                        probe = ref_new
                        seq = a.get("sequence")
                        if isinstance(seq, dict):          # a sequence: check its first frame
                            probe = ref_new + str(int(seq.get("start", 1))).zfill(int(seq.get("digits", 0)))
                        if image_exists is None or image_exists(probe):
                            if ref_key:
                                a[ref_key] = ref_new
                            fixes.append({"kind": "attachment path", "old": ref_old, "new": ref_new})
                        else:
                            # the file itself carries the extension in its name (or is missing): keep pointing at it
                            if not ref_key and a_new != a_old:
                                a["path"] = ref_old
                            fixes.append({"kind": "image reference (file name on disk has the extension)", "old": ref_old, "new": None})
                    if ref_key == "path" and isinstance(a.get("name"), str):   # next to a path, "name" is only a name
                        c = strip_ext(a["name"])
                        if c != a["name"]:
                            fixes.append({"kind": "attachment name", "old": a["name"], "new": c})
                            a["name"] = c
                    if "parent" in a:                     # linked mesh: parent attachment in the same slot
                        a["parent"] = att(slot_old, a["parent"])
                    if "skin" in a:
                        a["skin"] = ren(skin_map, a["skin"])
                    if "end" in a:                        # clipping: the slot where clipping ends
                        a["end"] = ren(slot_map, a["end"])
                new_atts[a_new] = a
            new_slots[ren(slot_map, slot_old)] = new_atts
        if skin_obj is not None:
            skin_obj["name"] = ren(skin_map, skin_name)
            if "attachments" in skin_obj:                 # some skins only list bones/constraints
                skin_obj["attachments"] = new_slots
            if isinstance(skin_obj.get("bones"), list):
                skin_obj["bones"] = [ren(bone_map, x) for x in skin_obj["bones"]]
            for kind in _CONSTRAINT_KINDS:
                if isinstance(skin_obj.get(kind), list):
                    skin_obj[kind] = [ren(con_maps[kind], x) for x in skin_obj[kind]]
        else:
            new_skins[ren(skin_map, skin_name)] = new_slots
    if isinstance(j.get("skins"), dict):
        j["skins"] = new_skins

    # ── events ──
    if isinstance(j.get("events"), dict):
        j["events"] = ren_keys(event_map, j["events"])

    # ── animations ──
    new_anims = {}
    for a_name, anim in animations.items():
        if isinstance(anim, dict):
            if isinstance(anim.get("bones"), dict):
                anim["bones"] = ren_keys(bone_map, anim["bones"])
            if isinstance(anim.get("slots"), dict):
                new = {}
                for slot_old, tl in anim["slots"].items():
                    if isinstance(tl, dict) and isinstance(tl.get("attachment"), list):
                        for k in tl["attachment"]:
                            if isinstance(k, dict) and k.get("name") is not None:
                                k["name"] = att(slot_old, k["name"])
                    new[ren(slot_map, slot_old)] = tl
                anim["slots"] = new
            for kind in _CONSTRAINT_KINDS:
                if isinstance(anim.get(kind), dict):
                    anim[kind] = ren_keys(con_maps[kind], anim[kind])
            if isinstance(anim.get("paths"), dict):            # Spine 3.x name of the path constraint timelines
                anim["paths"] = ren_keys(con_maps["path"], anim["paths"])
            for key in ("deform", "attachments"):          # {skin: {slot: {attachment: timelines}}}
                if isinstance(anim.get(key), dict):
                    anim[key] = {ren(skin_map, sk): {ren(slot_map, so): {att(so, an): tl for an, tl in (atts or {}).items()}
                                                      for so, atts in (slots_ or {}).items()}
                                 for sk, slots_ in anim[key].items()}
            for key in ("drawOrder", "draworder"):
                for k in (anim.get(key) or []):
                    for off in ((k or {}).get("offsets") or []):
                        if isinstance(off, dict) and "slot" in off:
                            off["slot"] = ren(slot_map, off["slot"])
            for ev in (anim.get("events") or []):
                if isinstance(ev, dict) and "name" in ev:
                    ev["name"] = ren(event_map, ev["name"])
        new_anims[ren(anim_map, a_name)] = anim
    if animations:
        j["animations"] = new_anims

    return fixes
