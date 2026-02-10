import re
import json
import sys
import os

P = sys.argv[1] if len(sys.argv) > 1 else r"test_files_from_collegues\\me\\game_intro_v2.spine"

def find_json_block(txt):
    # find first '{' that leads to a balanced JSON-like block
    start = txt.find('{')
    if start == -1:
        return None, None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(txt)):
        c = txt[i]
        if c == '\\' and not escape:
            escape = True
            continue
        if c == '"' and not escape:
            in_string = not in_string
        escape = False
        if in_string:
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return start, i+1
    return start, None

def quote_unquoted_keys(s):
    # Add quotes around unquoted keys (simple heuristic)
    # Matches: { key:  or , key:
    def repl(m):
        return f"{m.group(1)}\"{m.group(2)}\":"
    pat = re.compile(r'([\{,\s])([A-Za-z0-9_\-/]+)\s*:')
    prev = None
    out = s
    # iterate to handle nested levels
    for _ in range(6):
        prev = out
        out = pat.sub(repl, out)
    return out

def fix_common(js):
    # replace single quotes with double where safe (heuristic)
    js = re.sub(r"'(.*?)'", lambda m: '"' + m.group(1).replace('"', '\\"') + '"', js)
    # replace unquoted true/false/null (Python style) to JSON
    js = re.sub(r'\bTrue\b', 'true', js)
    js = re.sub(r'\bFalse\b', 'false', js)
    js = re.sub(r'\bNone\b', 'null', js)
    # remove trailing commas before } or ]
    js = re.sub(r',\s*(\}|\])', r'\1', js)
    return js

def attempt_parse(block):
    s = block
    s = quote_unquoted_keys(s)
    s = fix_common(s)
    try:
        return json.loads(s), None
    except Exception as e:
        return None, str(e)

def main(path):
    print('Reading:', path)
    if not os.path.exists(path):
        print('Not found')
        return
    with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
        txt = fh.read()
    start, end = find_json_block(txt)
    if start is None:
        print('No JSON block found')
        return
    if end is None:
        print('Found opening { at', start, 'but no matching closing }')
        # take rest of file
        block = txt[start:]
    else:
        block = txt[start:end]
    print('Extracted block length:', len(block))
    parsed, err = attempt_parse(block)
    if parsed is not None:
        print('Parsed JSON successfully. Top keys:', list(parsed.keys())[:20])
        outp = os.path.splitext(os.path.basename(path))[0] + '.extracted.json'
        outp = os.path.join('tools', outp)
        with open(outp, 'w', encoding='utf-8') as fh:
            json.dump(parsed, fh, indent=2)
        print('Wrote repaired JSON to', outp)
    else:
        print('Parsing failed:', err)
        sample = block[:2000]
        print('Sample (first 2000 chars):')
        print(sample)

if __name__ == '__main__':
    main(P)
