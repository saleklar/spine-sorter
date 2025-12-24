#!/usr/bin/env python3
"""Deep diagnostic tool for .spine packages.

Performs comprehensive checks:
1. ZIP structure and integrity.
2. JSON syntax and schema basics.
3. Path resolution (JSON attachments -> ZIP entries).
4. Image integrity (can Pillow open them?).
5. Case sensitivity checks.
6. Duplicate entries.

Usage: python deep_diagnose_spine.py <path_to_spine_file>
"""
import sys
import os
import zipfile
import json
import io
try:
    from PIL import Image
except ImportError:
    Image = None

def diagnose(spine_path):
    print(f"Diagnosing: {spine_path}")
    if not os.path.exists(spine_path):
        print("ERROR: File not found.")
        return

    if not zipfile.is_zipfile(spine_path):
        # Check if it might be a binary Spine file
        try:
            with open(spine_path, 'rb') as f:
                header = f.read(8)
                # Spine binary files often start with a version string or specific bytes, 
                # but simply not being a ZIP is a strong indicator it's a binary export if it's not empty.
                if len(header) > 0:
                    print("INFO: File is not a ZIP archive. It appears to be a binary .spine file (standard format).")
                    print("Diagnostic checks for ZIP structure skipped.")
                    return
        except Exception:
            pass
            
        print("ERROR: Not a valid ZIP file and could not be identified as a binary Spine file.")
        return

    issues = []
    warnings = []
    
    try:
        with zipfile.ZipFile(spine_path, 'r') as z:
            # 1. Check ZIP entries
            names = z.namelist()
            print(f"ZIP contains {len(names)} entries.")
            
            # Check for duplicates (case-insensitive)
            seen_lower = {}
            for n in names:
                lower = n.lower()
                if lower in seen_lower:
                    warnings.append(f"Duplicate filename (case-insensitive): {n} vs {seen_lower[lower]}")
                seen_lower[lower] = n

            # 2. Find JSON
            base_name = os.path.splitext(os.path.basename(spine_path))[0]
            expected_json = base_name + ".json"
            
            json_entry = None
            for n in names:
                if n == expected_json:
                    json_entry = n
                    break
                if n.lower() == expected_json.lower():
                    warnings.append(f"JSON name case mismatch: found '{n}', expected '{expected_json}'")
                    json_entry = n
            
            if not json_entry:
                # Fallback: look for any json
                jsons = [n for n in names if n.lower().endswith('.json')]
                if not jsons:
                    issues.append("CRITICAL: No JSON file found in archive.")
                    return
                if len(jsons) > 1:
                    warnings.append(f"Multiple JSON files found: {jsons}. Using {jsons[0]}")
                json_entry = jsons[0]
                issues.append(f"CRITICAL: Expected JSON '{expected_json}' not found. Found '{json_entry}' instead.")

            print(f"Analyzing JSON: {json_entry}")
            
            try:
                with z.open(json_entry) as f:
                    data = json.load(f)
            except Exception as e:
                issues.append(f"CRITICAL: Invalid JSON: {e}")
                return

            # 3. Check Skeleton
            skel = data.get('skeleton')
            if not skel:
                issues.append("CRITICAL: JSON missing 'skeleton' object.")
            else:
                images_path = skel.get('images')
                print(f"skeleton.images: '{images_path}'")
                if images_path not in ['./images/', 'images/']:
                    warnings.append(f"skeleton.images is '{images_path}'. Standard is './images/' or 'images/'.")

            # 4. Check Attachments
            # Collect all attachment paths
            attachment_paths = []
            
            def collect_paths(node):
                if isinstance(node, dict):
                    for k, v in node.items():
                        if k == 'path' and isinstance(v, str):
                            attachment_paths.append(v)
                        elif k == 'name' and isinstance(v, str) and 'path' not in node:
                             # Sometimes 'name' is used as path if path is missing
                             # But usually 'name' is the attachment name. 
                             # If it's an image attachment, name is the default path.
                             pass 
                        else:
                            collect_paths(v)
                    # Also check if this dict IS an attachment (has name/width/height usually, or type)
                    # If it's a region/mesh attachment and has no 'path', the key in the parent dict is the path
                    pass
                elif isinstance(node, list):
                    for item in node:
                        collect_paths(item)

            # A better way to walk skins specifically
            skins = data.get('skins', [])
            if isinstance(skins, dict):
                # Convert to list of dicts for uniform processing
                skins = [skins]
            
            # Helper to process skin dict
            def process_skin(skin_node):
                if not isinstance(skin_node, dict): return
                # skin_node is slot_name -> attachments
                for slot_name, attachments in skin_node.items():
                    if not isinstance(attachments, dict): continue
                    for attach_name, attach_data in attachments.items():
                        path = None
                        if isinstance(attach_data, dict):
                            path = attach_data.get('path')
                        
                        if not path:
                            path = attach_name # Default path is attachment name
                        
                        if path:
                            attachment_paths.append(path)

            if isinstance(skins, list):
                for s in skins:
                    if isinstance(s, dict):
                        # Check if it's a named skin object {name: "x", attachments: {...}}
                        if 'attachments' in s:
                            process_skin(s['attachments'])
                        else:
                            # Or a map of skins {skinName: {...}}
                            for k, v in s.items():
                                if isinstance(v, dict):
                                    process_skin(v)

            print(f"Found {len(attachment_paths)} attachment references.")
            
            # Verify paths
            missing_files = []
            for p in attachment_paths:
                # Construct expected path in ZIP
                # Spine joins skeleton.images + path + .png (if no extension)
                # But here we assume the ZIP structure matches what we wrote: images/skeleton/family/...
                
                # If skeleton.images is ./images/, and path is "hero/head", full is "images/hero/head"
                # We need to handle the extension.
                
                has_ext = os.path.splitext(p)[1] != ''
                candidates = []
                if has_ext:
                    candidates.append(p)
                else:
                    candidates.append(p + ".png")
                    candidates.append(p + ".jpg")
                    candidates.append(p + ".jpeg")
                
                # Prepend 'images/' if not present (assuming standard structure)
                # The script writes to 'images/...' in the zip.
                # The JSON path is relative to 'images/'.
                
                found = False
                for cand in candidates:
                    # Try with 'images/' prefix
                    try_paths = [
                        os.path.join('images', cand).replace('\\', '/'),
                        cand.replace('\\', '/') # In case path already includes images/
                    ]
                    
                    for tp in try_paths:
                        if tp in names:
                            found = True
                            break
                        # Case insensitive check
                        if tp.lower() in seen_lower:
                            found = True
                            # Check for exact case match
                            if seen_lower[tp.lower()] != tp:
                                warnings.append(f"Case mismatch: JSON '{p}' -> '{tp}' vs ZIP '{seen_lower[tp.lower()]}'")
                            break
                    if found: break
                
                if not found:
                    missing_files.append(p)

            if missing_files:
                issues.append(f"CRITICAL: {len(missing_files)} missing files referenced in JSON.")
                for m in missing_files[:10]:
                    issues.append(f"  - Missing: {m}")
                if len(missing_files) > 10:
                    issues.append(f"  - ... and {len(missing_files)-10} more")

            # 5. Check Image Integrity
            if Image:
                print("Checking image integrity...")
                bad_images = []
                for n in names:
                    if n.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                        try:
                            with z.open(n) as img_file:
                                # Read into memory to avoid seek issues with zip stream
                                buf = io.BytesIO(img_file.read())
                                with Image.open(buf) as im:
                                    im.verify()
                        except Exception as e:
                            bad_images.append(f"{n}: {e}")
                
                if bad_images:
                    issues.append(f"CRITICAL: {len(bad_images)} corrupt images found.")
                    for b in bad_images:
                        issues.append(f"  - {b}")
            else:
                warnings.append("Pillow not installed. Skipping image integrity check.")

    except Exception as e:
        issues.append(f"CRITICAL: Error reading ZIP: {e}")

    print("\n--- DIAGNOSTIC REPORT ---")
    if not issues and not warnings:
        print("SUCCESS: No issues found.")
    
    if warnings:
        print(f"\nWARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"- {w}")
            
    if issues:
        print(f"\nISSUES ({len(issues)}):")
        for i in issues:
            print(f"- {i}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python deep_diagnose_spine.py <path_to_spine_file>")
    else:
        diagnose(sys.argv[1])
