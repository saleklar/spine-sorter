#!/usr/bin/env python3
"""
Diagnostic script to find and optionally clean up spine_temp_ directories
"""
import os
import sys
import shutil

def find_temp_dirs(root="."):
    """Find all spine_temp_ directories"""
    temp_dirs = []
    for dirpath, dirnames, filenames in os.walk(root):
        for dirname in dirnames:
            if 'spine_temp_' in dirname:
                full_path = os.path.join(dirpath, dirname)
                temp_dirs.append(full_path)
    return temp_dirs

def main():
    print("Searching for spine_temp_ directories...")
    temps = find_temp_dirs()

    if not temps:
        print("No spine_temp_ directories found.")
        return

    print(f"\nFound {len(temps)} temporary directories:\n")
    for i, t in enumerate(temps, 1):
        try:
            size = sum(os.path.getsize(os.path.join(dirpath, filename))
                      for dirpath, dirnames, filenames in os.walk(t)
                      for filename in filenames)
            size_mb = size / (1024 * 1024)
            file_count = sum(len(filenames) for _, _, filenames in os.walk(t))
            print(f"{i}. {t}")
            print(f"   Size: {size_mb:.2f} MB, Files: {file_count}")
        except Exception as e:
            print(f"{i}. {t} - Error reading: {e}")

    print(f"\nTotal temp directories: {len(temps)}")

    # Ask if user wants to clean up
    response = input("\nDo you want to delete these directories? (yes/no): ").strip().lower()
    if response in ('yes', 'y'):
        deleted = 0
        failed = 0
        for t in temps:
            try:
                shutil.rmtree(t)
                print(f"Deleted: {t}")
                deleted += 1
            except Exception as e:
                print(f"Failed to delete {t}: {e}")
                failed += 1
        print(f"\nDeleted: {deleted}, Failed: {failed}")
    else:
        print("No directories deleted.")

if __name__ == "__main__":
    main()
