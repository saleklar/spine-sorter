"""Offline test: free-angle rotation+scale matching for beer can assets."""
import os, sys, math, itertools
import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim

FOLDER = r"d:\shared drives\design\trailer_trash\04_animation\01_source\spine\images\win_events\png"

def load_trimmed(path):
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None: return None, None
    if img.ndim == 3 and img.shape[2] == 4:
        mask = (img[:, :, 3] > 10).astype(np.uint8) * 255
        ys, xs = np.where(mask > 0)
        if len(xs) == 0: return None, None
        y0, y1, x0, x1 = ys.min(), ys.max()+1, xs.min(), xs.max()+1
        bgr = img[y0:y1, x0:x1, :3]; mask = mask[y0:y1, x0:x1]
    elif img.ndim == 3:
        bgr = img[:, :, :3]; mask = np.full(bgr.shape[:2], 255, np.uint8)
    else:
        bgr = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR); mask = np.full(img.shape, 255, np.uint8)
    return cv2.bitwise_and(bgr, bgr, mask=mask), mask

def try_match(small, large, flip=False):
    """Estimate similarity transform large->small via ORB, validate by warping. Returns (scale, spine_angle_deg, ssim) or None."""
    s_bgr, s_mask = small; l_bgr, l_mask = large
    if flip:
        l_bgr = cv2.flip(l_bgr, 1); l_mask = cv2.flip(l_mask, 1)
    orb = cv2.ORB_create(nfeatures=800)
    kp1, des1 = orb.detectAndCompute(l_bgr, None)   # large = source
    kp2, des2 = orb.detectAndCompute(s_bgr, None)   # small = destination
    if des1 is None or des2 is None or len(des1) < 8 or len(des2) < 8: return None
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    ms = bf.match(des1, des2)
    if len(ms) < 8: return None
    ms = sorted(ms, key=lambda m: m.distance)[:120]
    src = np.float32([kp1[m.queryIdx].pt for m in ms]).reshape(-1, 1, 2)
    dst = np.float32([kp2[m.trainIdx].pt for m in ms]).reshape(-1, 1, 2)
    M, inliers = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3.0)
    if M is None or inliers is None or inliers.sum() < 8: return None
    a, b = M[0, 0], M[1, 0]
    scale = math.hypot(a, b)
    if not (0.45 <= scale <= 1.05): return None
    theta_img = math.degrees(math.atan2(b, a))
    spine_angle = -theta_img
    # Validate: warp large onto small canvas
    sh, sw = s_bgr.shape[:2]
    warp_bgr = cv2.warpAffine(l_bgr, M, (sw, sh))
    warp_mask = cv2.warpAffine(l_mask, M, (sw, sh), flags=cv2.INTER_NEAREST)
    common = cv2.bitwise_and(warp_mask, s_mask)
    cov = common.sum() / max(1, s_mask.sum())  # overlap coverage of small content
    if cov < 0.90: return None
    g1 = cv2.cvtColor(cv2.bitwise_and(s_bgr, s_bgr, mask=common), cv2.COLOR_BGR2GRAY)
    g2 = cv2.cvtColor(cv2.bitwise_and(warp_bgr, warp_bgr, mask=common), cv2.COLOR_BGR2GRAY)
    s_score = ssim(g1, g2)
    if s_score < 0.90: return None
    return scale, spine_angle, s_score

def main():
    names = [f for f in os.listdir(FOLDER) if f.lower().endswith('.png') and 'can' in f.lower() and 'holder' not in f.lower() and 'glow' not in f.lower()]
    imgs = {}
    for n in names:
        t = load_trimmed(os.path.join(FOLDER, n))
        if t[0] is not None:
            imgs[n] = t
    print(f"Loaded {len(imgs)} can images")
    matched = set()
    # Sort by content pixel area ascending (small first)
    order = sorted(imgs.keys(), key=lambda n: int(imgs[n][1].sum()))
    found = 0
    for i, small_n in enumerate(order):
        if small_n in matched: continue
        for large_n in order[i+1:]:
            if large_n in matched: continue
            px_s = imgs[small_n][1].sum() / 255.0
            px_l = imgs[large_n][1].sum() / 255.0
            s_est = math.sqrt(px_s / max(1.0, px_l))
            if not (0.45 <= s_est <= 1.05):
                continue
            r = try_match(imgs[small_n], imgs[large_n], flip=False)
            tag = ''
            if r is None:
                r = try_match(imgs[small_n], imgs[large_n], flip=True)
                tag = ' +flipX'
            if r:
                scale, angle, sc = r
                print(f"MATCH: {small_n} -> {large_n}  scale={scale:.2f} angle={angle:+.1f}deg ssim={sc:.3f}{tag}")
                matched.add(small_n)
                found += 1
                break
    print(f"\nTotal free-angle matches: {found}")

if __name__ == '__main__':
    main()
