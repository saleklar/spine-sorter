import sys
import os
import re

# --- COPIED LOGIC FROM spine sorter 257.py ---
def detect_project_version(spine_path):
    # (Mock implementation or copy-paste regex logic)
    pass 

def find_best_spine_exe(target_version, combo_items):
    """
    Finds the best matching Spine executable from a list of (text, data) tuples.
    Prioritizes:
    1. Exact Version Match (e.g. 4.0.25 == 4.0.25)
    2. Major.Minor Match (e.g. 4.0.xx == 4.0.yy)
    """
    if not target_version:
        return None
        
    target_parts = target_version.split('.')
    if len(target_parts) < 2: return None
    
    # e.g. "4.0"
    target_major_minor = f"{target_parts[0]}.{target_parts[1]}"
    target_major = target_parts[0]
    
    best_exe = None
    best_score = -1 # 0=major only (removed), 1=major.minor match, 2=exact match
    
    for disp_text, exe_path in combo_items:
        if not exe_path: continue
        
        # Extract version from display text (e.g. "Spine (4.0.25) - ...")
        ver = None
        m = re.search(r'\((\d+\.\d+(?:\.\d+)?)\)', disp_text)
        if m:
            ver = m.group(1)
        
        if not ver: continue

        if ver == target_version:
            return exe_path # Exact match is best immediately
        
        ver_parts = ver.split('.')
        if len(ver_parts) >= 2:
            ver_major_minor = f"{ver_parts[0]}.{ver_parts[1]}"
            
            if ver_major_minor == target_major_minor:
                if best_score < 1:
                    best_score = 1
                    best_exe = exe_path
                    
    return best_exe

# --- TESTS ---
def test_logic():
    print("Running Logic Tests...")
    
    # Mock items: (Display Text, Path)
    combo_items = [
        ("Spine (4.1.24) - C:/Spine/4.1/Spine.exe", "C:/Spine/4.1/Spine.exe"),
        ("Spine Launcher (4.1.09) - C:/Spine/Launcher/Spine.exe", "C:/Spine/Launcher/Spine.exe"),
        ("Spine (3.8.99) - C:/Spine/3.8/Spine.exe", "C:/Spine/3.8/Spine.exe"),
    ]
    
    print("\nTest 1: Project 4.2.43 (Newer Minor Version)")
    # Expect: None (because 4.1 != 4.2) -> Falls back to -u
    res = find_best_spine_exe("4.2.43", combo_items)
    print(f"Result: {res}")
    if res is None:
        print("PASS: Correctly returned None (allowing fallback to -u)")
    else:
        print(f"FAIL: Matched {res} incorrectly (should be None)")

    print("\nTest 2: Project 4.1.24 (Exact Match)")
    # Expect: C:/Spine/4.1/Spine.exe
    res = find_best_spine_exe("4.1.24", combo_items)
    print(f"Result: {res}")
    if res and "4.1" in res:
        print("PASS: Found exact match")
    else:
        print("FAIL: Did not find exact match")

    print("\nTest 3: Project 4.1.50 (Minor Match)")
    # Expect: C:/Spine/4.1/Spine.exe (because 4.1 matches 4.1)
    res = find_best_spine_exe("4.1.50", combo_items)
    print(f"Result: {res}")
    if res and "4.1" in res:
        print("PASS: Found minor match")
    else:
        print("FAIL: Did not find minor match")

if __name__ == "__main__":
    test_logic()