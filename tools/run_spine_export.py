import subprocess, os, sys
spine = r"C:\Program Files\Spine\Spine.exe"
input_spine = os.path.normpath(r"z:\spine sorter v257\test_files_from_collegues\me\pop_ups.spine")
out_dir = os.path.normpath(r"z:\spine sorter v257\test_files_from_collegues\me\spine_temp_popups")
export_cfg = os.path.normpath(r"z:\spine sorter v257\default_export.json")
print('Running:', [spine, '-i', input_spine, '-o', out_dir, '-e', export_cfg])
try:
    p = subprocess.run([spine, '-i', input_spine, '-o', out_dir, '-e', export_cfg], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    print('returncode:', p.returncode)
    print('STDOUT:\n', p.stdout)
    print('STDERR:\n', p.stderr)
except Exception as e:
    print('Exception:', e)
    sys.exit(2)
