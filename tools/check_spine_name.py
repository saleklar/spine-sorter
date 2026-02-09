import zipfile, json, re, difflib, os, sys

SPINE_PATH = r"z:\spine sorter v257\test_files_from_collegues\muthahar\ambient.spine"

# Build wordlist from naming_conventions and USER_MANUAL
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
word_files = [
    os.path.join(root, 'naming_conventions', 'naming_conventions.txt'),
    os.path.join(root, 'USER_MANUAL.txt')
]
words = set(['ambient','idle','walk','run','jump','attack','hit','death','spawn','intro','anticipation'])
for p in word_files:
    try:
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8', errors='ignore') as fh:
                txt = fh.read()
            for w in re.findall(r"[A-Za-z0-9_]{3,}", txt):
                words.add(w.lower())
    except Exception:
        pass

print(f"Loaded {len(words)} words for fuzzy-check")


def extract_json_from_spine(path):
    try:
        with zipfile.ZipFile(path, 'r') as z:
            names = z.namelist()
            # prefer base-name.json
            base = os.path.splitext(os.path.basename(path))[0]
            candidates = [n for n in names if n.lower().endswith('.json')]
            jf = None
            for n in candidates:
                if os.path.basename(n).lower() == base.lower() + '.json':
                    jf = n; break
            if jf is None and candidates:
                jf = candidates[0]
            if jf is None:
                return None
            with z.open(jf) as f:
                return json.load(f)
    except Exception as e:
        # Not a zip: return None to allow binary scanning fallback
        # print('Error reading spine (not zip):', e)
        return None

j = extract_json_from_spine(SPINE_PATH)
if not j:
    print('No JSON found in spine package; scanning binary for tokens...')
    # try to scan binary for ASCII tokens
    try:
        with open(SPINE_PATH, 'rb') as bf:
            data = bf.read()
        # decode as latin1 to preserve bytes
        txt = data.decode('latin-1', errors='ignore')
        tokens = set(re.findall(r"[A-Za-z0-9_]{3,}", txt))
        tokens = {t.lower() for t in tokens}
        print(f'Found {len(tokens)} unique tokens in binary')
        # Basic Levenshtein distance
        def lev(a,b):
            la,lb = len(a), len(b)
            dp = [[0]*(lb+1) for _ in range(la+1)]
            for i in range(la+1): dp[i][0]=i
            for j in range(lb+1): dp[0][j]=j
            for i in range(1,la+1):
                for j in range(1,lb+1):
                    cost = 0 if a[i-1]==b[j-1] else 1
                    dp[i][j] = min(dp[i-1][j]+1, dp[i][j-1]+1, dp[i-1][j-1]+cost)
            return dp[la][lb]

        # look for tokens that are close to words in our dictionary (distance <=2)
        close_found = False
        for t in sorted(tokens):
            for w in ['ambient']:
                d = lev(t, w)
                if d <= 2:
                    print(f"Token '{t}' is edit-distance {d} from '{w}' -> suggestion: {w}")
                    close_found = True
        if not close_found:
            # fallback: also show closest difflib suggestions at lower cutoff
            for t in sorted(tokens):
                m = difflib.get_close_matches(t, list(words), n=1, cutoff=0.6)
                if m:
                    print(f"Token '{t}' -> suggestion: {m[0]}")
        sys.exit(0)
    except Exception as e:
        print('Binary scan failed:', e)
        sys.exit(1)

# look for skeleton names
skeletons = []
if isinstance(j, dict):
    skel = j.get('skeleton')
    if isinstance(skel, dict):
        for k in ('name','skeleton','spine'):
            v = skel.get(k)
            if isinstance(v, str) and v:
                skeletons.append(v)
# fallback: use filename
skeletons.append(os.path.splitext(os.path.basename(SPINE_PATH))[0])

skeletons = list(dict.fromkeys(skeletons))
print('Skeleton candidates:', skeletons)

for s in skeletons:
    print('\nChecking:', s)
    tokens = re.split(r'[^a-zA-Z0-9]+', s)
    for tok in tokens:
        if not tok or len(tok) < 3:
            continue
        low = tok.lower()
        if low in words:
            print(f" - token '{tok}' found in wordlist")
            continue
        m = difflib.get_close_matches(low, list(words), n=1, cutoff=0.7)
        if m:
            print(f" - token '{tok}' -> suggestion: {m[0]}")
        else:
            print(f" - token '{tok}' -> no suggestion")
