import os, sys, subprocess

if len(sys.argv) < 2:
    print('Usage: run_derive_all.py <export_folder>')
    sys.exit(2)
root = sys.argv[1]
if not os.path.isdir(root):
    print('Folder not found:', root)
    sys.exit(2)

script = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tools', 'derive_skel_dir.py')
if not os.path.isfile(script):
    print('derive_skel_dir.py not found at', script)
    sys.exit(2)

for dirpath, dirs, files in os.walk(root):
    for f in sorted(files):
        if f.lower().endswith('.json'):
            full = os.path.join(dirpath, f)
            print('JSON:', full)
            try:
                p = subprocess.run([sys.executable, script, full], capture_output=True, text=True, check=False)
                print(p.stdout.strip())
                if p.stderr:
                    print('ERR:', p.stderr.strip())
            except Exception as e:
                print('Exception running derive:', e)
            print('---')
