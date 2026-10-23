"""Disk-safety test for name_extensions: image references only change when the extension-less image exists, and the
asset files themselves are never touched (same names, same bytes before and after)."""
import hashlib
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from name_extensions import strip_name_extensions  # noqa: E402

PNG = bytes.fromhex("89504e470d0a1a0a")  # enough to tell files apart; content does not matter here


def snapshot(root):
    out = {}
    for d, _, files in os.walk(root):
        for f in files:
            p = os.path.join(d, f)
            out[os.path.relpath(p, root)] = hashlib.md5(open(p, "rb").read()).hexdigest()
    return out


def resolves(root, ref):
    base = os.path.join(root, *ref.split("/"))
    return any(os.path.isfile(base + e) for e in (".png", ".jpg", ".jpeg"))


def main():
    with tempfile.TemporaryDirectory() as tmp:
        images = os.path.join(tmp, "images")
        os.makedirs(os.path.join(images, "fx"))
        for rel in ("coin.png", "glow.png.png", "fx/star.png", "fx/spark01.png", "fx/spark02.png", "bg.jpg"):
            with open(os.path.join(images, *rel.split("/")), "wb") as f:
                f.write(PNG + rel.encode())
        before = snapshot(tmp)
        j = {
            "bones": [{"name": "root"}],
            "slots": [{"name": "s", "bone": "root", "attachment": "coin.png"}],
            "skins": [{"name": "default", "attachments": {"s": {
                "coin.png": {"width": 2, "height": 2},                        # name is the image; coin.png exists -> "coin"
                "glow.png": {"width": 2, "height": 2},                        # file is really "glow.png.png" -> keep pointing at it
                "star": {"path": "fx/star.png", "width": 2, "height": 2},     # path with extension, file exists -> "fx/star"
                "spark": {"path": "fx/spark.png", "width": 2, "height": 2,    # sequence: first frame fx/spark01 exists
                          "sequence": {"count": 2, "start": 1, "digits": 2}},
                "bg": {"path": "bg.JPG", "width": 2, "height": 2},           # .JPG in the reference, bg.jpg on disk -> "bg"
                "box.png": {"type": "boundingbox", "vertexCount": 3, "vertices": [0, 0, 1, 0, 0, 1]},   # no image
            }}}],
            "animations": {"a": {"slots": {"s": {"attachment": [{"time": 0, "name": "glow.png"}]}}}},
        }
        fixes = strip_name_extensions(j, image_exists=lambda ref: resolves(images, ref))
        after = snapshot(tmp)
        atts = j["skins"][0]["attachments"]["s"]
        problems = []
        if before != after:
            problems.append("files on disk changed")
        for name, a in atts.items():
            if a.get("type") == "boundingbox":
                continue
            ref = a.get("path", name)
            if "sequence" in a:
                ref += str(a["sequence"]["start"]).zfill(a["sequence"]["digits"])
            if not resolves(images, ref):
                problems.append("attachment %r points at a missing image %r" % (name, ref))
        expect = {"coin": None, "glow": "glow.png", "star": "fx/star", "spark": "fx/spark", "bg": "bg", "box": None}
        for name, path in expect.items():
            if name not in atts:
                problems.append("attachment %r missing (have %s)" % (name, sorted(atts)))
            elif atts[name].get("path") != path:
                problems.append("attachment %r path %r, expected %r" % (name, atts[name].get("path"), path))
        if j["slots"][0]["attachment"] != "coin" or j["animations"]["a"]["slots"]["s"]["attachment"][0]["name"] != "glow":
            problems.append("references not renamed: " + repr((j["slots"][0], j["animations"]["a"])))
        for f in fixes:
            print("  ", f)
        print("files on disk unchanged:", before == after)
        print("PROBLEMS:\n  " + "\n  ".join(problems) if problems else "all references resolve to existing images; OK")
        return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
