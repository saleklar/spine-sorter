# Replicates _sc_match_bruteforce from spine sorter 257.py (Phase 3c fallback)
# and validates against real data:
#  - coins_lvl_2_3 <-> coins_lvl_4_1 MUST match (~42 deg rotated copy)
#  - visually-different pairs MUST be rejected
import math, os, sys, time
import numpy as np
import cv2
from skimage.metrics import structural_similarity as ssim

FOLDER = r"e:\blazing_bullets_hold_and_win\04_animation\02_render\consolidation test\images\skeleton\png"
SC_MIN_SCALE, SC_MAX_SCALE = 0.45, 1.05


def _sc_load_trimmed(path):
	data = np.fromfile(path, dtype=np.uint8)
	img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
	if img is None:
		return None, None
	if img.ndim == 2:
		img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
	if img.shape[2] == 3:
		img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
	alpha = img[:, :, 3]
	mask = (alpha > 15).astype(np.uint8) * 255
	ys, xs = np.where(mask > 0)
	if len(xs) == 0:
		return None, None
	y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
	bgr = img[y0:y1, x0:x1, :3].copy()
	m = mask[y0:y1, x0:x1].copy()
	bgr[m == 0] = 0
	return bgr, m


def sc_match_bruteforce(small_path, large_path, flip=False):
	try:
		s_bgr, s_mask = _sc_load_trimmed(small_path)
		l_bgr, l_mask = _sc_load_trimmed(large_path)
		if s_bgr is None or l_bgr is None:
			return None
		if flip:
			l_bgr = cv2.flip(l_bgr, 1); l_mask = cv2.flip(l_mask, 1)
		px_s = float((s_mask > 0).sum()); px_l = float((l_mask > 0).sum())
		if px_s < 64 or px_l < 64:
			return None
		sc_est = math.sqrt(px_s / max(1.0, px_l))
		if not (SC_MIN_SCALE <= sc_est <= SC_MAX_SCALE):
			return None
		hs, ws = s_bgr.shape[:2]
		hL, wL = l_bgr.shape[:2]
		diag = int(math.ceil(math.hypot(hL, wL) * sc_est)) + 4
		g_small_full = cv2.cvtColor(s_bgr, cv2.COLOR_BGR2GRAY)

		def _try_angle(ang, shifts=(-1, 0, 1)):
			M_r = cv2.getRotationMatrix2D((wL/2.0, hL/2.0), ang, sc_est)
			M_r[0, 2] += diag/2.0 - wL/2.0
			M_r[1, 2] += diag/2.0 - hL/2.0
			rb = cv2.warpAffine(l_bgr, M_r, (diag, diag))
			rm = cv2.warpAffine(l_mask, M_r, (diag, diag), flags=cv2.INTER_NEAREST)
			ys_r, xs_r = np.where(rm > 0)
			if len(xs_r) == 0:
				return None
			y0r, y1r = ys_r.min(), ys_r.max()+1
			x0r, x1r = xs_r.min(), xs_r.max()+1
			rb = rb[y0r:y1r, x0r:x1r]; rm = rm[y0r:y1r, x0r:x1r]
			if abs(rb.shape[0]-hs) > 3 or abs(rb.shape[1]-ws) > 3:
				return None
			Hc = max(rb.shape[0], hs); Wc = max(rb.shape[1], ws)
			def _padc(b, th, tw):
				return cv2.copyMakeBorder(b, 0, th-b.shape[0], 0, tw-b.shape[1], cv2.BORDER_CONSTANT, value=0)
			g1p = _padc(g_small_full, Hc, Wc)
			m1p = _padc(s_mask, Hc, Wc)
			g2p = _padc(cv2.cvtColor(rb, cv2.COLOR_BGR2GRAY), Hc, Wc)
			m2p = _padc(rm, Hc, Wc)
			best_s_loc, best_g2, best_m2 = -1.0, g2p, m2p
			for dy_b in shifts:
				for dx_b in shifts:
					if dx_b == 0 and dy_b == 0:
						g2s, m2s = g2p, m2p
					else:
						M_s = np.float32([[1, 0, dx_b], [0, 1, dy_b]])
						g2s = cv2.warpAffine(g2p, M_s, (Wc, Hc))
						m2s = cv2.warpAffine(m2p, M_s, (Wc, Hc), flags=cv2.INTER_NEAREST)
					try:
						s_loc = ssim(g1p, g2s)
					except Exception:
						continue
					if s_loc > best_s_loc:
						best_s_loc, best_g2, best_m2 = s_loc, g2s, m2s
			return best_s_loc, g1p, m1p, best_g2, best_m2

		best_ang, best_val = None, -1.0
		for ang in range(0, 360, 6):
			r = _try_angle(ang)
			if r and r[0] > best_val:
				best_val, best_ang = r[0], ang
		if best_ang is None or best_val < 0.55:
			return None
		fine_best = None
		for ang_f in range(best_ang-5, best_ang+6):
			r = _try_angle(ang_f % 360, shifts=(-2, -1, 0, 1, 2))
			if r and (fine_best is None or r[0] > fine_best[0]):
				fine_best = r; best_ang = ang_f % 360
		if fine_best is None:
			return None
		s_score, g1p, m1p, g2p, m2p = fine_best
		if s_score < 0.93:
			return None
		common = cv2.bitwise_and(m1p, m2p)
		cov = common.sum() / max(1, m1p.sum())
		if cov < 0.90:
			return None
		leftover = float(((m2p > 0) & (m1p == 0)).sum())
		if (m2p > 0).sum() > 0 and leftover / float((m2p > 0).sum()) > 0.06:
			return None
		diff_g = cv2.absdiff(g1p, g2p)
		diff_g[common == 0] = 0
		err_m = (diff_g > 48).astype(np.uint8)
		err_m = cv2.morphologyEx(err_m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
		content_px = max(1, int((common > 0).sum()))
		if float(err_m.sum()) / content_px > 0.010:
			return None
		n_lbl, _li, stats_cc, _ce = cv2.connectedComponentsWithStats(err_m, connectivity=8)
		if n_lbl > 1 and (float(stats_cc[1:, cv2.CC_STAT_AREA].max()) / content_px) > 0.005:
			return None
		spine_angle = float(((best_ang + 180.0) % 360.0) - 180.0)
		return sc_est, spine_angle, s_score
	except Exception as e:
		print("  EXC:", e)
		return None


def run_pair(a, b, expect_match):
	pa = os.path.join(FOLDER, a + ".png")
	pb = os.path.join(FOLDER, b + ".png")
	t0 = time.time()
	r = sc_match_bruteforce(pa, pb, flip=False)
	fl = False
	if r is None:
		r = sc_match_bruteforce(pa, pb, flip=True)
		fl = True
	dt = time.time() - t0
	matched = r is not None
	ok = matched == expect_match
	tag = "PASS" if ok else "FAIL"
	if r:
		print(f"[{tag}] {a} <-> {b}: MATCH scale={r[0]:.3f} angle={r[1]:.1f} ssim={r[2]:.4f} flip={fl} ({dt:.2f}s)")
	else:
		print(f"[{tag}] {a} <-> {b}: no match ({dt:.2f}s)")
	return ok


if __name__ == "__main__":
	cases = [
		# genuine rotated copy found by brute-force scan (42 deg, ssim 0.96)
		("coins_lvl_2_3", "coins_lvl_4_1", True),
		# visually similar but genuinely different poses (scan scores <= 0.59) -> reject
		("coins_lvl_4_15", "coins_lvl_4_17", False),
		("coins_lvl_2_3", "coins_lvl_4_15", False),
		("coins_lvl_4_1", "coins_lvl_4_17", False),
	]

	all_ok = all(run_pair(*c) for c in cases)
	print("\nRESULT:", "ALL PASS" if all_ok else "SOME FAILED")
	sys.exit(0 if all_ok else 1)
