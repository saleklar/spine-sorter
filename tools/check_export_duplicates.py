import os
import sys
import json
import re
import hashlib
from collections import defaultdict

try:
    from PIL import Image
except Exception:
    Image = None

def collect_from_json(obj, image_paths, json_image_paths):
    if isinstance(obj, str):
        if re.search(r'\.(?:png|jpg|jpeg|webp|bmp|tga)$', obj, flags=re.IGNORECASE):
            image_paths.add(obj)
            json_image_paths.add(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and re.search(r'\.(?:png|jpg|jpeg|webp|bmp|tga)$', k, flags=re.IGNORECASE):
                image_paths.add(k)
                json_image_paths.add(k)
            collect_from_json(v, image_paths, json_image_paths)
    elif isinstance(obj, list):
        for v in obj:
            collect_from_json(v, image_paths, json_image_paths)

def collect_keys(obj, image_paths, json_image_paths):
    IGNORE_KEYS = {
        'skins', 'skeleton', 'slots', 'bones', 'animations', 'attachment', 'attachments',
        'audio', 'path', 'name', 'width', 'height', 'x', 'y', 'scale', 'scalex', 'scaley',
        'translate', 'translatex', 'translatey', 'rotate', 'rotation', 'rgba', 'color',
        'blend', 'start', 'time', 'delay', 'sequence', 'mode', 'count', 'length', 'hash',
        'icon', 'logo', 'parent', 'value', 'spine'
    }
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str):
                kl = k.lower()
                if re.search(r'\.(?:png|jpg|jpeg|webp|bmp|tga)$', k, flags=re.IGNORECASE):
                    image_paths.add(k)
                    json_image_paths.add(k)
                elif kl not in IGNORE_KEYS:
                    json_image_paths.add(k)
                if kl in ['path', 'name'] and isinstance(v, str):
                    image_paths.add(v)
                    json_image_paths.add(v)
            collect_keys(v, image_paths, json_image_paths)
    elif isinstance(obj, list):
        for v in obj:
            collect_keys(v, image_paths, json_image_paths)

def find_images_in_folder(folder):
    imgs = []
    for root, dirs, files in os.walk(folder):
        for f in files:
            if re.search(r'\.(?:png|jpg|jpeg|webp|bmp|tga)$', f, flags=re.IGNORECASE):
                imgs.append(os.path.join(root, f))
    return imgs

def pixel_hash(path):
    try:
        if Image is None:
            raise RuntimeError('PIL unavailable')
        im = Image.open(path)
        rgba = im.convert('RGBA')
        raw = rgba.tobytes()
        h = hashlib.sha1(raw).hexdigest()
        return h, rgba.size
    except Exception:
        # fallback to file SHA1
        h = hashlib.sha1()
        with open(path, 'rb') as fh:
            while True:
                chunk = fh.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest(), None

def clean_name(fn):
    bn = os.path.splitext(os.path.basename(fn))[0]
    parts = bn.split('-')
    keep = []
    for p in parts:
        if re.match(r'^\d', p):
            break
        keep.append(p)
    return '-'.join(keep) if keep else bn

def main(folder):
    if not os.path.isdir(folder):
        print('Folder not found:', folder)
        return 1
    print('Inspecting export folder:', folder)
    # find JSONs
    jsons = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith('.json')]
    if not jsons:
        print('No JSON files found in folder')
        return 1
    print('Found JSONs:', [os.path.basename(p) for p in jsons])

    all_images = find_images_in_folder(folder)
    print('Total image files in folder:', len(all_images))

    for jpath in jsons:
        print('\n--- Processing skeleton JSON:', os.path.basename(jpath), '---')
        with open(jpath, 'r', encoding='utf-8', errors='ignore') as fh:
            try:
                obj = json.load(fh)
            except Exception as e:
                print('Could not parse JSON:', e)
                continue

        image_paths = set()
        json_image_paths = set()
        collect_from_json(obj, image_paths, json_image_paths)
        collect_keys(obj, image_paths, json_image_paths)

        # build explicit and bare refs
        explicit_refs = set()
        bare_refs = set()
        for p in json_image_paths:
            pn = p.replace('\\', '/').lower()
            if re.search(r'\.(?:png|jpg|jpeg|webp|bmp|tga)$', p, flags=re.IGNORECASE):
                explicit_refs.add(pn)
                explicit_refs.add(os.path.basename(pn))
                explicit_refs.add(os.path.splitext(os.path.basename(pn))[0])
            else:
                bare_refs.add(pn)

        # resolve images in folder that match refs
        resolved = []
        for img in all_images:
            rel = os.path.relpath(img, folder).replace('\\', '/').lower()
            bn = os.path.basename(img).lower()
            bn_noext = os.path.splitext(bn)[0]
            matched = False
            if explicit_refs:
                if rel in explicit_refs or bn in explicit_refs or bn_noext in explicit_refs:
                    matched = True
                else:
                    for e in explicit_refs:
                        if e in rel or rel in e:
                            matched = True
                            break
            if not matched and bare_refs:
                if bn_noext in bare_refs or bn in bare_refs:
                    matched = True
                else:
                    for b in bare_refs:
                        if b in bn_noext or bn_noext in b or b in rel or rel in b:
                            matched = True
                            break
            if matched:
                resolved.append(img)

        print('Referenced images resolved:', len(resolved))

        # compute pixel hashes
        hash_map = defaultdict(list)
        for img in resolved:
            try:
                h, size = pixel_hash(img)
                key = (h, size)
                hash_map[key].append(img)
            except Exception as e:
                print('Hash failed for', img, e)

        # report groups where multiple different filenames exist for same pixel hash
        reported = False
        for key, files in hash_map.items():
            if len(files) > 1:
                # check if multiple distinct basenames
                bns = set(os.path.basename(f) for f in files)
                if len(bns) > 1:
                    if not reported:
                        print('\nIdentical-image groups in this skeleton:')
                        reported = True
                    print('Group (hash,size)=', key)
                    for f in files:
                        print(' -', os.path.relpath(f, folder))

        if not reported:
            print('No identical-image groups detected for this skeleton.')

    return 0

if __name__ == '__main__':
    folder = sys.argv[1] if len(sys.argv) > 1 else r'tools\\temp_export'
    sys.exit(main(folder))
