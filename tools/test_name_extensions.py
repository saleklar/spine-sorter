"""Test for name_extensions.strip_name_extensions on real Spine skeletons.

For each skeleton: every name (bones, slots, skins, attachments, animations, events, constraints) is "polluted" by
plain text replacement of the exact JSON string "name" -> "name.png" (or .PNG / .jpg), which changes definitions and
all references at once, independently of the code under test. Stripping must give back exactly the original data.

usage: python tools/test_name_extensions.py <folder or .json files...>
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from name_extensions import strip_name_extensions  # noqa: E402

# Spine JSON property keys: a name equal to one of these is not polluted (text replacement would hit the key too)
KEYS = set("""name bone bones parent length x y rotation scaleX scaleY shearX shearY transform inherit skin skins color dark
attachment attachments blend type path uvs triangles vertices hull edges width height sequence count start digits setup
target mix mixRotate mixX mixY mixScaleX mixScaleY mixShearY softness bendPositive compress stretch uniform order time
value value2 curve offsets slot slots events animations ik physics drawOrder deform rgba rgb rgba2 rgb2 alpha translate
scale shear end position spacing positionMode spacingMode rotateMode lengths closed constantSpeed int float string
audio volume balance skeleton hash spine fps images audio local relative skinRequired default offset delay mode index
spacing inertia strength damping massInverse wind gravity limit step scaleX scaleY fixed paths icon
region mesh linkedmesh boundingbox point clipping normal additive multiply screen rotate stepped""".split())


def plain_values(o, out):
    """String values that are not names (bone icons, enum values...): polluting them would be a test artefact."""
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ("icon", "type", "blend", "rotateMode", "positionMode", "spacingMode", "inherit", "transform", "mode") and isinstance(v, str):
                out.add(v)
            plain_values(v, out)
    elif isinstance(o, list):
        for v in o:
            plain_values(v, out)
    return out


def collect_names(j):
    names = set()
    names.update(b["name"] for b in j.get("bones", []))
    names.update(s["name"] for s in j.get("slots", []))
    for k in ("ik", "transform", "path", "physics"):
        names.update(c["name"] for c in j.get(k, []))
    names.update((j.get("events") or {}).keys())
    names.update((j.get("animations") or {}).keys())
    skins = j.get("skins") or []
    for sk in (skins if isinstance(skins, list) else [{"name": n, "attachments": v} for n, v in skins.items()]):
        names.add(sk.get("name", "default"))
        for atts in (sk.get("attachments") or {}).values():
            names.update(atts.keys())
            for a in atts.values():
                if isinstance(a, dict) and a.get("type", "region") in ("region", "mesh", "linkedmesh"):   # image references only
                    for key in ("path", "name"):
                        if isinstance(a.get(key), str):
                            names.add(a[key])
    skip = KEYS | plain_values(j, set())
    return {n for n in names if isinstance(n, str) and n and n not in skip}


def pollute(text, names):
    exts = [".png", ".PNG", ".jpg", ".jpeg"]
    for i, n in enumerate(sorted(names, key=len, reverse=True)):
        q = json.dumps(n, ensure_ascii=False)
        text = text.replace(q, json.dumps(n + exts[i % len(exts)], ensure_ascii=False))
    return text


def first_diffs(a, b, path, out):
    if len(out) >= 3:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in a:
            if k not in b:
                out.append("%s: key %r missing (have %s)" % (path, k, [x for x in b if x not in a][:3]))
            elif a[k] != b[k]:
                first_diffs(a[k], b[k], path + "/" + str(k), out)
        for k in b:
            if k not in a:
                out.append("%s: unexpected key %r" % (path, k))
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            if x != y:
                first_diffs(x, y, "%s[%d]" % (path, i), out)
    else:
        out.append("%s: expected %r, got %r" % (path, a, b))
    return out


def main(paths):
    files = []
    for p in paths:
        files += glob.glob(os.path.join(p, "**", "*.json"), recursive=True) if os.path.isdir(p) else [p]
    failed = 0
    for f in sorted(files):
        try:
            text = open(f, encoding="utf-8").read()
            orig = json.loads(text)
        except (ValueError, UnicodeDecodeError):
            continue
        if not isinstance(orig, dict) or "bones" not in orig:
            continue
        names = collect_names(orig)
        polluted = json.loads(pollute(text, names))
        fixes = strip_name_extensions(polluted)
        ok = polluted == orig
        failed += not ok
        print(("OK  " if ok else "FAIL") + "  %-34s %4d names polluted, %4d fixes" % (os.path.basename(f), len(names), len(fixes)))
        if not ok:
            for d in first_diffs(orig, polluted, "", [])[:3]:
                print("      " + d)
    print("\n%d failed" % failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
