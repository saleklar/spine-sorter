#!/usr/bin/env python3
"""Validate .spine package structure for Spine auto-import.

Checks performed:
- archive contains a JSON whose name matches the package base name
- `skeleton.images` is set to './images/' (or 'images/')
- attachment `path` values point under the images/ folder and corresponding files exist in the archive

Usage: python tools/validate_spine_package.py path/to/package.spine
"""
import sys
import zipfile
import json
import os


def validate(pkg_path):
    if not os.path.isfile(pkg_path):
        print('Not found:', pkg_path)
        return 2
    if not zipfile.is_zipfile(pkg_path):
        print('Not a zip/.spine:', pkg_path)
        return 2

    base = os.path.splitext(os.path.basename(pkg_path))[0]
    expected_json = base + '.json'

    with zipfile.ZipFile(pkg_path, 'r') as z:
        names = z.namelist()
        ok = True
        if expected_json not in names:
            print('ERROR: package JSON name does not match package base: expected', expected_json)
            # show any JSONs found
            js = [n for n in names if n.lower().endswith('.json')]
            print(' JSONs in archive:', js)
            ok = False
        else:
            print('Found package JSON:', expected_json)
            raw = z.read(expected_json)
            try:
                obj = json.loads(raw)
            except Exception as e:
                print('ERROR: could not parse JSON inside package:', e)
                return 2

            skel = obj.get('skeleton') if isinstance(obj, dict) else None
            if not isinstance(skel, dict):
                print('WARNING: no skeleton object in JSON')
            else:
                images_field = skel.get('images')
                if images_field not in ('./images/', 'images/'):
                    print("WARNING: skeleton.images is", images_field, "— Spine expects './images/' or 'images/' for packaged images")
                else:
                    print('skeleton.images ok:', images_field)

            # collect attachments from skins
            missing_files = []
            def walk_attach(x):
                if isinstance(x, dict):
                    for k, v in x.items():
                        if k == 'path' and isinstance(v, str):
                            # path should be relative to skeleton.images (no leading 'images/')
                            check = v.replace('\\', '/')
                            
                            # Try exact match first
                            arc_path = os.path.normpath(os.path.join('images', check)).replace('\\','/')
                            if arc_path in names:
                                continue
                                
                            # Try appending .png
                            if arc_path + '.png' in names:
                                continue
                                
                            # Try appending .jpg
                            if arc_path + '.jpg' in names:
                                continue
                                
                            missing_files.append((v, arc_path))
                        else:
                            walk_attach(v)
                elif isinstance(x, list):
                    for it in x:
                        walk_attach(it)

            if 'skins' in obj:
                walk_attach(obj['skins'])

            if missing_files:
                print('ERROR: some attachment image paths were not found inside archive:')
                for p, arc in missing_files:
                    print(' - declared:', p, 'expected archive path:', arc)
                ok = False
            else:
                print('All declared attachment paths exist inside archive (or no attachments declared).')

    return 0 if ok else 1


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: validate_spine_package.py path/to/package.spine')
        sys.exit(2)
    sys.exit(validate(sys.argv[1]))
