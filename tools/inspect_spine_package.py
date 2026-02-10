import sys
import os
import zipfile
import json

P = sys.argv[1] if len(sys.argv) > 1 else r"test_files_from_collegues\me\game_intro_v2.spine"

def main(path):
    print('Inspecting:', path)
    if not os.path.exists(path):
        print('File not found')
        return
    print('Size:', os.path.getsize(path), 'bytes')
    try:
        if zipfile.is_zipfile(path):
            print('Detected ZIP-based .spine package')
            with zipfile.ZipFile(path, 'r') as z:
                names = z.namelist()
                print('Entries:', len(names))
                for n in names[:200]:
                    print(' ', n)
                # try to find JSONs
                jfiles = [n for n in names if n.lower().endswith('.json')]
                print('Found JSON files inside:', len(jfiles))
                for j in jfiles[:50]:
                    print('  -', j)
                # attempt to read and parse first JSON
                if jfiles:
                    with z.open(jfiles[0]) as fh:
                        try:
                            data = json.load(fh)
                            print('First JSON parsed; keys:', list(data.keys())[:20])
                        except Exception as e:
                            print('Could not parse JSON inside package:', e)
        else:
            print('Not a zip archive. Trying to read as text JSON...')
            with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
                txt = fh.read()
                # try to find a JSON object start
                if '{' in txt:
                    idx = txt.find('{')
                    sample = txt[idx:idx+2000]
                    print('Found "{" at offset', idx)
                    # try parse
                    try:
                        obj = json.loads(sample + '\n}')
                        print('Parsed sample JSON keys:', list(obj.keys())[:20])
                    except Exception as e:
                        print('Could not parse sample JSON:', e)
                else:
                    print('No JSON-like content found')
    except Exception as e:
        print('Inspection failed:', e)

if __name__ == '__main__':
    main(P)
