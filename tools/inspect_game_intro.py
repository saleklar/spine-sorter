import json
import os
import re

P = os.path.join('test_files_from_collegues', 'him', 'output_2', 'game_intro.json')

def collect_from_json(x, image_paths, json_image_paths):
    if isinstance(x, str):
        if re.search(r'\.(?:png|jpg|jpeg|webp|bmp|tga)$', x, flags=re.IGNORECASE):
            image_paths.add(x)
            json_image_paths.add(x)
    elif isinstance(x, dict):
        for k, v in x.items():
            if isinstance(k, str) and re.search(r'\.(?:png|jpg|jpeg|webp|bmp|tga)$', k, flags=re.IGNORECASE):
                image_paths.add(k)
                json_image_paths.add(k)
            collect_from_json(v, image_paths, json_image_paths)
    elif isinstance(x, list):
        for v in x:
            collect_from_json(v, image_paths, json_image_paths)

def collect_keys(x, image_paths, json_image_paths):
    IGNORE_KEYS = {
        'skins', 'skeleton', 'slots', 'bones', 'animations', 'attachment', 'attachments',
        'audio', 'path', 'name', 'width', 'height', 'x', 'y', 'scale', 'scalex', 'scaley',
        'translate', 'translatex', 'translatey', 'rotate', 'rotation', 'rgba', 'color',
        'blend', 'start', 'time', 'delay', 'sequence', 'mode', 'count', 'length', 'hash',
        'icon', 'logo', 'parent', 'value', 'spine'
    }
    if isinstance(x, dict):
        for k, v in x.items():
            if isinstance(k, str):
                kl = k.lower()
                if re.search(r'\.(?:png|jpg|jpeg|webp|bmp|tga)$', k, flags=re.IGNORECASE):
                    image_paths.add(k)
                    json_image_paths.add(k)
                elif kl not in IGNORE_KEYS:
                    # bare key could be image reference
                    json_image_paths.add(k)
                if kl in ['path', 'name'] and isinstance(v, str):
                    image_paths.add(v)
                    json_image_paths.add(v)
            collect_keys(v, image_paths, json_image_paths)
    elif isinstance(x, list):
        for v in x:
            collect_keys(v, image_paths, json_image_paths)

def main():
    if not os.path.exists(P):
        print('File not found:', P)
        return
    with open(P, 'r', encoding='utf-8', errors='ignore') as fh:
        obj = json.load(fh)

    image_paths = set()
    json_image_paths = set()
    collect_from_json(obj, image_paths, json_image_paths)
    collect_keys(obj, image_paths, json_image_paths)

    print('Total explicit image paths (with ext):', len([p for p in json_image_paths if re.search(r"\\.(?:png|jpg|jpeg|webp|bmp|tga)$", p, flags=re.IGNORECASE)]))
    print('Total json_image_paths (including bare keys):', len(json_image_paths))
    print('\nSample json_image_paths:')
    for i,p in enumerate(sorted(list(json_image_paths))[:200]):
        print(' ', p)

    # Skeleton section info
    skel = obj.get('skeleton', {})
    print('\nSkeleton fields:')
    for k,v in skel.items():
        print(' ', k, ':', v)

    # report unusual entries
    noext = [p for p in json_image_paths if not re.search(r'\\.(?:png|jpg|jpeg|webp|bmp|tga)$', p, flags=re.IGNORECASE)]
    if noext:
        print('\nEntries without image extension (bare keys or paths):')
        for p in noext[:200]:
            print(' ', p)

if __name__ == '__main__':
    main()
