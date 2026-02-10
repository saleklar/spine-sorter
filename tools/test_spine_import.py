import subprocess, os, sys

def main():
    spine = os.path.normpath(r"C:\Program Files\Spine\Spine.exe")
    fixed = os.path.normpath(r"z:\spine sorter v257\test_files_from_collegues\me\anticiation_fixed.json")
    out = os.path.normpath(r"z:\spine sorter v257\test_output_fixed.spine")
    print('Spine exe:', spine)
    print('Fixed JSON:', fixed)
    if not os.path.exists(spine):
        print('Spine exe not found at path; aborting')
        sys.exit(2)
    if not os.path.exists(fixed):
        print('Fixed JSON not found; aborting')
        sys.exit(3)
    cmd = [spine, '-i', fixed, '-o', out, '--import']
    print('Running:', ' '.join(cmd))
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        print('returncode:', p.returncode)
        if p.stdout:
            print('STDOUT:\n', p.stdout)
        if p.stderr:
            print('STDERR:\n', p.stderr)
        if os.path.exists(out):
            print('Output exists:', out, 'size=', os.path.getsize(out))
    except Exception as e:
        print('Exception running Spine:', e)

if __name__ == '__main__':
    main()
