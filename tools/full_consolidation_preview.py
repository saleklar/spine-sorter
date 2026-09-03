# Full-folder consolidation preview: replicates Phase 3c logic
# (ORB freeform matcher + new brute-force rotation fallback for small sprites)
# over every pair, then union-finds groups to show final consolidation result.
import math, os, sys, time, itertools
import numpy as np
import cv2
from skimage.metrics import structural_similarity as ssim

sys.path.insert(0, os.path.dirname(__file__))
from verify_bruteforce_rotation import sc_match_bruteforce, _sc_load_trimmed, FOLDER

SC_MIN_SCALE, SC_MAX_SCALE = 0.45, 1.05


def sc_match_free(small_path, large_path, flip=False):
	"""Mirror of the app's ORB freeform matcher with all gates."""
	try:
		s_bgr, s_mask = _sc_load_trimmed(small_path)
		l_bgr, l_mask = _sc_load_trimmed(large_path)
		if s_bgr is None or l_bgr is None:
			return None
		if flip:
			l_bgr = cv2.flip(l_bgr, 1); l_mask = cv2.flip(l_mask, 1)
		orb = cv2.ORB_create(nfeatures=800)
		kp1, des1 = orb.detectAndCompute(l_bgr, None)
		kp2, des2 = orb.detectAndCompute(s_bgr, None)
		if des1 is None or des2 is None or len(des1) < 8 or len(des2) < 8:
			return None
		bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
		ms = bf.match(des1, des2)
		if len(ms) < 8:
			return None
		ms = sorted(ms, key=lambda m: m.distance)[:120]
		src = np.float32([kp1[m.queryIdx].pt for m in ms]).reshape(-1, 1, 2)
		dst = np.float32([kp2[m.trainIdx].pt for m in ms]).reshape(-1, 1, 2)
		M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3.0)
		if M is None or inl is None or inl.sum() < 8:
			return None
		a_c, b_c = M[0, 0], M[1, 0]
		scale = math.hypot(a_c, b_c)
		if not (SC_MIN_SCALE <= scale <= SC_MAX_SCALE):
			return None
		theta = math.degrees(math.atan2(b_c, a_c))
		sh, sw = s_bgr.shape[:2]
		wb = cv2.warpAffine(l_bgr, M, (sw, sh))
		wm = cv2.warpAffine(l_mask, M, (sw, sh), flags=cv2.INTER_NEAREST)
		common = cv2.bitwise_and(wm, s_mask)
		if common.sum() / max(1, s_mask.sum()) < 0.90:
			return None
		l_px = float((l_mask > 0).sum())
		exp = l_px * scale * scale
		in_canvas = float((wm > 0).sum())
		if exp > 0 and in_canvas < 0.97 * exp:
			return None
		leftover = float(((wm > 0) & (s_mask == 0)).sum())
		if in_canvas > 0 and leftover / in_canvas > 0.02:
			return None
		s_common = cv2.bitwise_and(s_bgr, s_bgr, mask=common)
		w_common = cv2.bitwise_and(wb, wb, mask=common)
		g1 = cv2.cvtColor(s_common, cv2.COLOR_BGR2GRAY)
		g2 = cv2.cvtColor(w_common, cv2.COLOR_BGR2GRAY)
		sv = ssim(g1, g2)
		if sv < 0.90:
			return None
		# Blurred color gate (grayscale is blind on saturated hues)
		common_er = cv2.erode(common, np.ones((5, 5), np.uint8))
		er_px = int((common_er > 0).sum())
		if er_px > 400:
			blur1 = cv2.GaussianBlur(s_common, (0, 0), 2.0)
			blur2 = cv2.GaussianBlur(w_common, (0, 0), 2.0)
			dcol = cv2.absdiff(blur1, blur2).max(axis=2).astype(np.float32)
			dcol[common_er == 0] = 0
			if float(dcol[common_er > 0].mean()) > 8.0:
				return None
			if float((dcol > 24).sum()) / er_px > 0.02:
				return None
		diff = cv2.absdiff(g1, g2); diff[common == 0] = 0
		em = (diff > 48).astype(np.uint8)
		em = cv2.morphologyEx(em, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
		cpx = max(1, int((common > 0).sum()))
		if float(em.sum()) / cpx > 0.010:
			return None
		n, _l, st, _c = cv2.connectedComponentsWithStats(em, connectivity=8)
		if n > 1 and float(st[1:, cv2.CC_STAT_AREA].max()) / cpx > 0.005:
			return None
		return scale, -theta, sv
	except Exception:
		return None


files = sorted(f for f in os.listdir(FOLDER) if f.lower().endswith(".png"))
info = {}
for f in files:
	b, m = _sc_load_trimmed(os.path.join(FOLDER, f))
	info[f] = (m.shape if m is not None else None, int((m > 0).sum()) if m is not None else 0)

parent = {f: f for f in files}
def find(x):
	while parent[x] != x:
		parent[x] = parent[parent[x]]; x = parent[x]
	return x
def union(a, b):
	ra, rb = find(a), find(b)
	if ra != rb:
		parent[ra] = rb

t0 = time.time()
edges = []
for a, b in itertools.combinations(files, 2):
	# smaller content first (matcher expects small->large)
	if info[a][1] > info[b][1]:
		a, b = b, a
	pa, pb = os.path.join(FOLDER, a), os.path.join(FOLDER, b)
	res, how, fl = None, None, False
	sm = max(info[a][0]); lg = max(info[b][0])
	for flip in (False, True):
		r = sc_match_free(pa, pb, flip=flip)
		if r:
			res, how, fl = r, "orb", flip; break
	if res is None and sm <= 96 and lg <= 96:
		for flip in (False, True):
			r = sc_match_bruteforce(pa, pb, flip=flip)
			if r:
				res, how, fl = r, "bruteforce", flip; break
	if res:
		edges.append((a, b, res, how, fl))
		union(a, b)
		print(f"MATCH [{how}] {a} -> {b}: scale={res[0]:.3f} angle={res[1]:.1f} ssim={res[2]:.4f} flip={fl}")

groups = {}
for f in files:
	groups.setdefault(find(f), []).append(f)

print(f"\n=== Consolidation groups ({time.time()-t0:.1f}s) ===")
n_saved = 0
for root, members in sorted(groups.items()):
	if len(members) > 1:
		n_saved += len(members) - 1
		print(f"  KEEP {members[0]}  <- consolidates: {', '.join(members[1:])}")
uniq = [m for m in groups.values() if len(m) == 1]
print(f"\n{len(files)} files -> {len(groups)} unique ({n_saved} consolidated, {len(uniq)} singletons)")
