#!/usr/bin/env python3
"""
Reverted loader: executes the backup file for commit 8ed63b7.

This file replaces the current modified main script and loads
the backup snapshot stored as `.git_old_spine_sorter_8ed63b7.py`.
If you prefer a literal copy instead of delegation, I can paste
the full backup contents into this file.
"""
import os
import sys

def _load_backup():
    base = os.path.dirname(os.path.abspath(__file__))
    backup = os.path.join(base, '.git_old_spine_sorter_8ed63b7.py')
    if not os.path.exists(backup):
        raise FileNotFoundError(f"Backup file not found: {backup}")
    with open(backup, 'r', encoding='utf-8') as f:
        code = f.read()
    # Execute backup in this module's globals so imports and definitions behave as before
    exec(compile(code, backup, 'exec'), globals())

if __name__ == '__main__':
    try:
        _load_backup()
    except Exception as e:
        sys.stderr.write(f"Failed to load backup script: {e}\n")
        raise
