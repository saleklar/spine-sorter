# Diagnose false-positive scaled-duplicate matches on Mummy Mayhem ruby piles.
# Runs the exact Phase 3c gates (ORB freeform + bruteforce fallback) on every
# pile pair and reports each gate's value so we can see WHY a false pair passes.
import math, os, sys, itertools
import numpy as np
import cv2
from skimage.metrics import structural_similarity as ssim

FOLDER = sys.argv[1] if len(sys.argv) > 1 else r"D:\Shared drives\Design\Mr_Oinksters_Mummy_Mayhem\04_Animation\01_Source\Spine\images\persistence\png\red"
PREFIX = sys.argv[2] if len(sys.argv) > 2 else "pile"
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


def sc_match_free_verbose(small_path, large_path, flip=False):
    """Same gates as _sc_match_free but prints every gate value."""
    tag = f"{os.path.basename(small_path)} <- {os.path.basename(large_path)} flip={flip}"
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
    cov = common.sum() / max(1, s_mask.sum())
    l_px = float((l_mask > 0).sum())
    exp = l_px * scale * scale
    in_canvas = float((wm > 0).sum())
    conserve = in_canvas / exp if exp > 0 else 0
    leftover = float(((wm > 0) & (s_mask == 0)).sum())
    left_frac = leftover / in_canvas if in_canvas > 0 else 0
    g1 = cv2.cvtColor(cv2.bitwise_and(s_bgr, s_bgr, mask=common), cv2.COLOR_BGR2GRAY)
    g2 = cv2.cvtColor(cv2.bitwise_and(wb, wb, mask=common), cv2.COLOR_BGR2GRAY)
    sv = ssim(g1, g2)
    # NEW blurred color gate (mirrors app fix)
    s_common = cv2.bitwise_and(s_bgr, s_bgr, mask=common)
    w_common = cv2.bitwise_and(wb, wb, mask=common)
    common_er = cv2.erode(common, np.ones((5, 5), np.uint8))
    er_px = int((common_er > 0).sum())
    blur_mean, f24 = 0.0, 0.0
    if er_px > 400:
        blur1 = cv2.GaussianBlur(s_common, (0, 0), 2.0)
        blur2 = cv2.GaussianBlur(w_common, (0, 0), 2.0)
        dcol = cv2.absdiff(blur1, blur2).max(axis=2).astype(np.float32)
        dcol[common_er == 0] = 0
        blur_mean = float(dcol[common_er > 0].mean())
        f24 = float((dcol > 24).sum()) / er_px
    diff = cv2.absdiff(g1, g2); diff[common == 0] = 0
    em = (diff > 48).astype(np.uint8)
    em = cv2.morphologyEx(em, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    cpx = max(1, int((common > 0).sum()))
    err_frac = float(em.sum()) / cpx
    n, _l, st, _c = cv2.connectedComponentsWithStats(em, connectivity=8)
    blob = float(st[1:, cv2.CC_STAT_AREA].max()) / cpx if n > 1 else 0.0
    inliers = int(inl.sum())
    print(f"  {tag}")
    print(f"    inliers={inliers} scale={scale:.3f} angle={theta:.1f} cov={cov:.3f} "
          f"conserve={conserve:.3f} leftover={left_frac:.4f} ssim={sv:.4f} "
          f"err_frac={err_frac:.5f} max_blob={blob:.5f} blur_mean={blur_mean:.2f} f24={f24:.4f}")
    passed = (cov >= 0.90 and conserve >= 0.97 and left_frac <= 0.02
              and sv >= 0.90 and err_frac <= 0.010 and blob <= 0.005
              and blur_mean <= 8.0 and f24 <= 0.02)
    print(f"    => {'MATCH (would consolidate!)' if passed else 'rejected'}")
    return (scale, -theta, sv) if passed else None


files = sorted(f for f in os.listdir(FOLDER) if f.lower().endswith(".png") and f.startswith(PREFIX))
print(f"Testing {len(files)} pile files in {FOLDER}\n")
matches = []
for a, b in itertools.combinations(files, 2):
    pa, pb = os.path.join(FOLDER, a), os.path.join(FOLDER, b)
    _, ma = _sc_load_trimmed(pa)
    _, mb = _sc_load_trimmed(pb)
    if ma is None or mb is None:
        continue
    if (ma > 0).sum() > (mb > 0).sum():
        pa, pb = pb, pa; a, b = b, a
    for flip in (False, True):
        r = sc_match_free_verbose(pa, pb, flip=flip)
        if r:
            matches.append((a, b, flip, r))
            break

print(f"\n=== {len(matches)} pair(s) PASSED all gates (false positives if visually different) ===")
for a, b, fl, r in matches:
    print(f"  {a} <-> {b} flip={fl} scale={r[0]:.3f} angle={r[1]:.1f} ssim={r[2]:.4f}")
