import zipfile
import os
import datetime
import sys


def make_backup(src, dst_dir=None):
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    base = os.path.basename(src.rstrip('\\/'))
    if dst_dir is None:
        dst_dir = os.path.dirname(src.rstrip('\\/'))
    dst = os.path.join(dst_dir, f"{base}_backup_{ts}.zip")
    with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(src):
            for f in files:
                full = os.path.join(root, f)
                arc = os.path.relpath(full, start=src)
                z.write(full, arc)
    return dst


if __name__ == '__main__':
    src = r"Z:\spine sorter v257"
    try:
        dst = make_backup(src)
        print('Created:', dst)
        sys.exit(0)
    except Exception as e:
        print('Error:', e)
        sys.exit(2)
