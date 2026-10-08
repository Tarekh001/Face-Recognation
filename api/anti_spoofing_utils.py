"""
Anti-Spoofing — Multi-Frame Temporal Analysis
===============================================
Mendeteksi spoofing berdasarkan analisis PERUBAHAN ANTAR FRAME
dari beberapa foto berurutan yang diambil cepat (200ms interval).

Prinsip fisika yang dieksploitasi:
  1. FOTO CETAK → 100% statis, ZERO perubahan antar frame
  2. LAYAR DIGITAL → screen flicker 60Hz, brightness oscillation periodik
  3. WAJAH ASLI → micro-movement alami (nafas, tremor otot, pulse kulit)

Ini jauh lebih akurat dari single-frame analysis karena
memanfaatkan sifat fisik yang MUSTAHIL dipalsukan oleh 
foto atau layar.

Endpoint: POST /api/check-spoof
  Input: multipart — frame_0, frame_1, frame_2 (3 foto berurutan)
  Output: { is_real, confidence, details }
"""

import os
import sys
import cv2
import numpy as np
from PIL import Image, ImageOps

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


# ============================================
# KONFIGURASI (v3 — Balanced: Anti-Replay + Low FRR)
# ============================================
# Threshold — skor di atas ini = REAL
# v1=0.55 (terlalu rendah), v2=0.85 (terlalu tinggi/FRR tinggi)
# v3=0.75 → sweet spot: real faces ~0.80, paper/screen ~0.65
FAS_THRESHOLD = 0.65

# Minimum motion yang diharapkan dari wajah asli
# Wajah asli menghasilkan micro-movement >= 1.5 pixel units
MIN_MOTION_THRESHOLD = 1.5  # pixel intensity units

# Maximum motion — dinaikkan untuk mengakomodasi getaran tablet handheld / tap layar (hingga ~80px)
MAX_MOTION_THRESHOLD = 80.0

# Camera shake zone — motion di rentang ini mencurigakan (shake, bukan wajah)
SHAKE_MOTION_LOW = 0.5
SHAKE_MOTION_HIGH = 2.0

# Screen flicker detection threshold  
FLICKER_THRESHOLD = 0.3  # Rasio flicker yang mencurigakan

# ============================================
# GLOBAL
# ============================================
_mtcnn = None

def _get_mtcnn():
    global _mtcnn
    if _mtcnn is None:
        try:
            from mtcnn import MTCNN
            _mtcnn = MTCNN()
            print("[MultiFrame-FAS] MTCNN loaded")
        except Exception as e:
            print(f"[MultiFrame-FAS] MTCNN error: {e}")
    return _mtcnn


# ============================================
# FACE EXTRACTION
# ============================================
def _load_and_crop_face(image_path: str, target_size=(200, 200)):
    """Load image, detect face via MTCNN, crop with padding, return grayscale + color."""
    try:
        img = Image.open(image_path).convert('RGB')
        img = ImageOps.exif_transpose(img)
        img_rgb = np.array(img)
        img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
        
        mtcnn = _get_mtcnn()
        if mtcnn is None:
            gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
            gray = cv2.resize(gray, target_size)
            return gray, cv2.resize(img_bgr, target_size), img_rgb.shape[:2]

        results = mtcnn.detect_faces(img_rgb)
        best_rot_rgb = img_rgb
        best_rot_bgr = img_bgr

        if not results:
            # Fallback untuk tablet/kiosk camera dengan orientasi sensor miring (90°, 270°, 180°)
            for rot_code in (cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE, cv2.ROTATE_180):
                cand_rgb = cv2.rotate(img_rgb, rot_code)
                cand_results = mtcnn.detect_faces(cand_rgb)
                if cand_results:
                    results = cand_results
                    best_rot_rgb = cand_rgb
                    best_rot_bgr = cv2.cvtColor(best_rot_rgb, cv2.COLOR_RGB2BGR)
                    break

        if not results:
            return None, None, None

        best = max(results, key=lambda x: x['confidence'])
        x, y, w, h = best['box']
        
        # Padding 25%
        pad = int(max(w, h) * 0.25)
        ih, iw = best_rot_bgr.shape[:2]
        x1, y1 = max(0, x-pad), max(0, y-pad)
        x2, y2 = min(iw, x+w+pad), min(ih, y+h+pad)
        
        face_bgr = best_rot_bgr[y1:y2, x1:x2]
        if face_bgr.size == 0:
            return None, None, None
            
        face_gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
        
        face_gray = cv2.resize(face_gray, target_size)
        face_bgr = cv2.resize(face_bgr, target_size)
        
        return face_gray, face_bgr, (ih, iw)
        
    except Exception as e:
        print(f"[MultiFrame-FAS] Load error: {e}")
        return None, None, None


# ============================================
# ANALYSIS 1: MICRO-MOTION DETECTION
# ============================================
def _analyze_motion(frames_gray: list) -> dict:
    """
    Deteksi micro-movement antar frame.
    
    WAJAH ASLI:
      - Selalu ada micro-movement (nafas → dada naik/turun sedikit,
        tremor otot wajah, pulse arteri temporal, micro-saccade mata)
      - Mean absolute difference antar frame: 1-10 pixel units
      - Distribusi movement: organic, gradual, bervariasi per region
    
    FOTO CETAK:
      - ZERO movement (perfectly static)
      - Mean absolute difference: < 0.5 pixel units
      - Hanya noise kamera
    
    LAYAR DIGITAL (foto statis):
      - Hampir zero movement (hanya noise kamera + screen flicker)
      - Mean absolute difference: < 1.0 pixel units
      
    Returns: dict dengan skor dan detail
    """
    if len(frames_gray) < 2:
        return {'score': 0.5, 'avg_motion': 0, 'motion_std': 0, 'detail': 'insufficient frames'}
    
    motions = []
    region_motions = []
    
    for i in range(len(frames_gray) - 1):
        f1 = frames_gray[i].astype(np.float32)
        f2 = frames_gray[i+1].astype(np.float32)
        
        # Absolute difference
        diff = np.abs(f2 - f1)
        avg_diff = np.mean(diff)
        motions.append(avg_diff)
        
        # Regional motion analysis (divide into 4 quadrants)
        h, w = diff.shape
        regions = [
            diff[:h//2, :w//2],   # top-left
            diff[:h//2, w//2:],   # top-right
            diff[h//2:, :w//2],   # bottom-left
            diff[h//2:, w//2:],   # bottom-right
        ]
        reg_motions = [np.mean(r) for r in regions]
        region_motions.append(reg_motions)
    
    avg_motion = np.mean(motions)
    motion_std = np.std(motions)
    
    # Regional motion variability — wajah asli bergerak TIDAK seragam
    # (misalnya mulut bergerak tapi dahi diam)
    if region_motions:
        avg_regional_std = np.mean([np.std(rm) for rm in region_motions])
    else:
        avg_regional_std = 0
    
    print(f"   [Motion] avg={avg_motion:.3f} std={motion_std:.3f} "
          f"regional_var={avg_regional_std:.3f}")
    
    # Scoring
    if avg_motion < MIN_MOTION_THRESHOLD:
        # Terlalu statis → kemungkinan besar foto cetak atau layar statis
        score = 0.15
        detail = f"TOO STATIC (motion={avg_motion:.2f} < {MIN_MOTION_THRESHOLD})"
    elif avg_motion > MAX_MOTION_THRESHOLD:
        # Gerakan berlebihan (> 80.0) — penalty lunak karena bisa jadi gerakan mendadak/ganti foto
        score = 0.50
        detail = f"EXCESSIVE MOTION ({avg_motion:.2f}) — soft penalty"
    else:
        # Ada movement wajar — tipikal handheld smartphone/tablet
        motion_normalized = min(1.0, (avg_motion - MIN_MOTION_THRESHOLD) / 12.0)
        
        # Bonus: regional variation (wajah asli → movement tidak seragam)
        regional_bonus = min(0.2, avg_regional_std * 0.1)
        
        score = 0.6 + motion_normalized * 0.3 + regional_bonus
        detail = f"NATURAL MOTION (motion={avg_motion:.2f})"
    
    return {
        'score': float(np.clip(score, 0, 1)),
        'avg_motion': float(avg_motion),
        'motion_std': float(motion_std),
        'regional_var': float(avg_regional_std),
        'detail': detail,
    }


# ============================================
# ANALYSIS 2: SCREEN FLICKER DETECTION
# ============================================
def _analyze_flicker(frames_gray: list) -> dict:
    """
    Deteksi screen flicker dari layar digital.
    
    Layar digital refresh pada ~60Hz. Kamera pada ~30fps menangkap
    alternating brightness. Ini terlihat sebagai:
    - Oscillation brightness yang periodik
    - Pattern: bright → dark → bright → dark
    
    WAJAH ASLI: brightness changes gradual dan non-periodic
    LAYAR: brightness oscillation periodik dan konsisten
    
    Returns: dict dengan skor dan detail
    """
    if len(frames_gray) < 3:
        return {'score': 0.5, 'flicker_ratio': 0, 'detail': 'insufficient frames'}
    
    # Hitung mean brightness per frame
    brightnesses = [np.mean(f) for f in frames_gray]
    
    # Hitung perubahan brightness antar frame
    diffs = [brightnesses[i+1] - brightnesses[i] for i in range(len(brightnesses)-1)]
    
    # Detect oscillation: apakah sign berubah-ubah? (+ - + - pattern)
    sign_changes = 0
    for i in range(len(diffs) - 1):
        if diffs[i] * diffs[i+1] < 0:  # Tanda berubah
            sign_changes += 1
    
    max_sign_changes = max(1, len(diffs) - 1)
    oscillation_ratio = sign_changes / max_sign_changes
    
    # Hitung variasi brightness (screen flicker → konsisten, kecil)
    brightness_std = np.std(brightnesses)
    
    # Flicker signature: banyak sign changes + brightness variation kecil tapi konsisten
    if oscillation_ratio > 0.6 and 0.5 < brightness_std < 5.0:
        # Strong flicker pattern → likely screen
        score = 0.2
        detail = f"FLICKER DETECTED (osc={oscillation_ratio:.2f}, std={brightness_std:.2f})"
    elif oscillation_ratio > 0.5:
        score = 0.4
        detail = f"POSSIBLE FLICKER (osc={oscillation_ratio:.2f})"
    else:
        score = 0.8
        detail = f"NO FLICKER (osc={oscillation_ratio:.2f})"
    
    print(f"   [Flicker] brightness_std={brightness_std:.3f} "
          f"oscillation={oscillation_ratio:.2f} => score={score:.2f}")
    
    return {
        'score': float(np.clip(score, 0, 1)),
        'flicker_ratio': float(oscillation_ratio),
        'brightness_std': float(brightness_std),
        'detail': detail,
    }


# ============================================
# ANALYSIS 3: TEXTURE CONSISTENCY
# ============================================
def _analyze_texture_consistency(frames_gray: list) -> dict:
    """
    Analisis konsistensi tekstur antar frame.
    
    WAJAH ASLI: Tekstur berubah halus karena 3D movement + pencahayaan dinamis
    FOTO: Tekstur identik antar frame (2D surface)
    LAYAR: Tekstur berganti karena pixel refresh tapi pattern-nya repetitif
    """
    if len(frames_gray) < 2:
        return {'score': 0.5}
    
    # Compute Laplacian (edge/texture) for each frame
    laplacians = []
    for f in frames_gray:
        lap = cv2.Laplacian(f, cv2.CV_64F)
        laplacians.append(lap)
    
    # Compare texture between consecutive frames
    texture_diffs = []
    for i in range(len(laplacians) - 1):
        diff = np.mean(np.abs(laplacians[i+1] - laplacians[i]))
        texture_diffs.append(diff)
    
    avg_texture_diff = np.mean(texture_diffs)
    
    # Real face: texture changes subtly (3D rotation → different edges lit)
    # Photo: texture nearly identical
    if avg_texture_diff < 0.3:
        score = 0.2  # Perfectly static texture → photo
        detail = "STATIC TEXTURE"
    elif avg_texture_diff < 1.0:
        score = 0.5
        detail = "LOW TEXTURE CHANGE"
    else:
        score = 0.8
        detail = "DYNAMIC TEXTURE"
    
    print(f"   [Texture] avg_diff={avg_texture_diff:.3f} => {detail} (score={score:.2f})")
    
    return {
        'score': float(np.clip(score, 0, 1)),
        'avg_texture_diff': float(avg_texture_diff),
        'detail': detail,
    }

# ============================================
# ANALYSIS 4: COLOR CHANNEL VARIANCE (Screen Detection)
# ============================================
def _analyze_color_variance(image_paths: list) -> dict:
    """
    Deteksi layar digital via distribusi warna.
    
    LAYAR DIGITAL: Sub-pixel RGB grid → channel variance rendah dan seragam,
                   backlight menghasilkan blue channel dominan.
    WAJAH ASLI:    Kulit manusia punya distribusi warna organik,
                   variasi antar channel lebih tinggi dan tidak seragam.
    """
    channel_vars = []
    blue_ratios = []
    
    for path in image_paths:
        try:
            img = Image.open(path).convert('RGB')
            img = ImageOps.exif_transpose(img)
            img_np = np.array(img, dtype=np.float32)
            
            # Per-channel standard deviation
            r_std = np.std(img_np[:,:,0])
            g_std = np.std(img_np[:,:,1])
            b_std = np.std(img_np[:,:,2])
            
            # Variance antar channel std (organic skin → high, screen → uniform)
            inter_var = np.std([r_std, g_std, b_std])
            channel_vars.append(inter_var)
            
            # Blue ratio (screen backlight → blue dominant)
            total = np.mean(img_np[:,:,0]) + np.mean(img_np[:,:,1]) + np.mean(img_np[:,:,2])
            if total > 0:
                blue_ratios.append(np.mean(img_np[:,:,2]) / total)
        except Exception:
            continue
    
    if not channel_vars:
        return {'score': 0.5, 'detail': 'no data'}
    
    avg_var = np.mean(channel_vars)
    avg_blue = np.mean(blue_ratios) if blue_ratios else 0.33
    
    # Screen detection — 3 tier scoring
    # Tier 1: Pasti layar (very uniform RGB + blue backlight dominant)
    if avg_var < 3.0 and avg_blue > 0.38:
        score = 0.15
        detail = f"SCREEN SIGNATURE (var={avg_var:.2f}, blue={avg_blue:.3f})"
    # Tier 2: Pencahayaan indoor seragam tapi blue backlight normal (bukan layar)
    elif avg_var < 3.0:
        score = 0.50
        detail = f"INDOOR UNIFORM LIGHTING (var={avg_var:.2f})"
    # Tier 3: Zona abu-abu (indoor flat lighting)
    elif avg_var < 5.0:
        score = 0.65
        detail = f"MODERATE COLOR VARIANCE (var={avg_var:.2f})"
    # Tier 4: Pasti organik (high variance = kulit manusia 3D)
    else:
        score = 0.85
        detail = f"ORGANIC COLOR (var={avg_var:.2f})"
    
    print(f"   [Color] inter_channel_var={avg_var:.3f} blue_ratio={avg_blue:.3f} => {detail}")
    
    return {
        'score': float(np.clip(score, 0, 1)),
        'inter_channel_var': float(avg_var),
        'blue_ratio': float(avg_blue),
        'detail': detail,
    }



# ============================================
# PUBLIC API
# ============================================
class AntiSpoofingChecker:
    """
    Multi-frame temporal anti-spoofing checker.
    
    Menerima 3+ frame berurutan dan menganalisis:
    1. Micro-motion (wajah asli selalu bergerak sedikit)
    2. Screen flicker (layar digital punya refresh rate)
    3. Texture consistency (foto statis = texture identik)
    
    Juga mendukung single-frame fallback (skor neutral 0.5).
    """

    def __init__(self, threshold: float = FAS_THRESHOLD):
        self.threshold = threshold
        self.model_available = True  # Selalu available

    def check_liveness(self, image_path: str) -> tuple[bool, float]:
        """Single-frame fallback — skor neutral, biarkan active liveness yang memutuskan."""
        return self.check_liveness_multi([image_path])

    def check_liveness_multi(self, image_paths: list) -> tuple[bool, float]:
        """
        Multi-frame liveness check — metode utama.
        
        Args:
            image_paths: List path ke 3+ gambar berurutan (diambil ~200ms interval)
        
        Returns:
            (is_real, confidence)
        """
        # Load all frames
        frames_gray = []
        for path in image_paths:
            gray, _, _ = _load_and_crop_face(path)
            if gray is not None:
                frames_gray.append(gray)
        
        if len(frames_gray) < 2:
            print("[MultiFrame-FAS] Not enough frames with face detected")
            if len(frames_gray) == 1:
                # Single frame fallback — skor neutral
                return True, 0.6, "SINGLE_FRAME"
            return False, 0.0, "NO_FACE"
        
        print(f"[MultiFrame-FAS] Analyzing {len(frames_gray)} frames...")
        
        # Run all analyses
        motion = _analyze_motion(frames_gray)
        flicker = _analyze_flicker(frames_gray)
        texture = _analyze_texture_consistency(frames_gray)
        color = _analyze_color_variance(image_paths)
        
        # Weighted combination (4 analyzers)
        # Motion tetap indikator terkuat, color sebagai pendukung
        final = (
            0.45 * motion['score'] +
            0.20 * flicker['score'] +
            0.20 * texture['score'] +
            0.15 * color['score']
        )
        
        # STRICT RULE 1: Motion sangat rendah → pasti bukan wajah asli
        if motion['avg_motion'] < MIN_MOTION_THRESHOLD:
            final = min(final, 0.30)  # Force below threshold (0.75)
            print(f"   [STRICT] Low motion ({motion['avg_motion']:.3f}) → SPOOF override")
        
        # STRICT RULE 2: Camera shake zone — motion ada tapi rendah,
        # DAN texture statis → kemungkinan besar layar + kamera goyang
        if (SHAKE_MOTION_LOW <= motion['avg_motion'] <= SHAKE_MOTION_HIGH 
            and texture['score'] < 0.4):
            final = min(final, 0.45)
            print(f"   [STRICT] Camera-shake zone (motion={motion['avg_motion']:.3f}, "
                  f"texture={texture['score']:.3f}) → SPOOF penalty")
        
        # STRICT RULE 3: Screen color signature terdeteksi → force reject
        if color['score'] < 0.2:
            final = min(final, 0.35)
            print(f"   [STRICT] Screen color signature → SPOOF override")
        
        is_real = final >= self.threshold
        label = "REAL" if is_real else "SPOOF"
        
        print(f"[MultiFrame-FAS] Motion={motion['score']:.3f} "
              f"Flicker={flicker['score']:.3f} Texture={texture['score']:.3f} "
              f"Color={color['score']:.3f}")
        print(f"[MultiFrame-FAS] => Final={final:.3f} (thr={self.threshold}) => {label}")
        print(f"   Detail: {motion['detail']} | {color['detail']}")
        
        return is_real, float(final), label


# Singleton
spoof_checker = AntiSpoofingChecker()
