import os
import cv2
import numpy as np
import pickle
from keras_facenet import FaceNet
from mtcnn import MTCNN
from PIL import Image, ImageOps
from scipy.spatial.distance import cosine

import threading

# ============================================
# INISIALISASI MODEL (Satu kali saat startup)
# ============================================
facenet = FaceNet()
model = facenet.model
detector = MTCNN()

print("✅ [INIT] FaceNet + MTCNN Face Detector berhasil dimuat.")

# ============================================
# FACE DETECTION & ALIGNMENT (MTCNN)
# ============================================
def _is_upright_face(face):
    """
    Memeriksa apakah deteksi wajah dalam orientasi tegak (mata di atas mulut).
    MTCNN keypoints: left_eye, right_eye, nose, mouth_left, mouth_right.
    """
    if not face or 'keypoints' not in face:
        return True
    kp = face['keypoints']
    eye_y = (kp['left_eye'][1] + kp['right_eye'][1]) / 2.0
    mouth_y = (kp['mouth_left'][1] + kp['mouth_right'][1]) / 2.0
    # Pada orientasi tegak normal, mata HARUS berada di atas mulut (y mata < y mulut)
    if eye_y >= mouth_y:
        return False
    # Jarak horizontal mata harus lebih besar dari perbedaan vertikal
    dx = abs(kp['right_eye'][0] - kp['left_eye'][0])
    dy = abs(kp['right_eye'][1] - kp['left_eye'][1])
    if dx < dy * 0.7:
        return False
    return True


def _filter_best_real_face(results, min_size=45, require_upright=True):
    """
    Menyaring deteksi wajah MTCNN untuk mengabaikan noise/speck kecil (< min_size px).
    Hanya mengembalikan wajah valid berukuran cukup dan orientasi tegak (jika require_upright).
    Mengutamakan confidence terlebih dahulu, lalu area.
    """
    if not results:
        return None
    valid = [f for f in results if f['box'][2] >= min_size and f['box'][3] >= min_size]
    if require_upright:
        upright = [f for f in valid if _is_upright_face(f)]
        if upright:
            valid = upright
    if not valid:
        return None
    return max(valid, key=lambda f: (f['confidence'], f['box'][2] * f['box'][3]))


def align_and_square_crop(img_rgb, face, target_size=(160, 160), margin_ratio=1.35):
    """
    1. Menyelaraskan kemiringan wajah (eye alignment) jika landmark tersedia (-35° s/d 35°).
    2. Melakukan crop simetris persegi (1:1 aspect ratio) dengan padding border reflection.
       Hal ini mencegah wajah tertekan/terdistorsi saat di-resize ke target_size (160x160)
       dan mencegah dahi terpotong jika wajah mepet batas atas (y <= 17).
    """
    ih, iw = img_rgb.shape[:2]
    x, y, w, h = face['box']
    kp = face.get('keypoints')
    
    aligned_img = img_rgb
    cx = x + w / 2.0
    cy = y + h * 0.45  

    if kp:
        lx, ly = kp['left_eye']
        rx, ry = kp['right_eye']
        dx = rx - lx
        dy = ry - ly
        tilt_angle = np.degrees(np.arctan2(dy, dx))
        
        
        if 1.5 < abs(tilt_angle) < 35.0:
            eye_center = (float((lx + rx) / 2.0), float((ly + ry) / 2.0))
            M = cv2.getRotationMatrix2D(eye_center, tilt_angle, 1.0)
            aligned_img = cv2.warpAffine(
                img_rgb, M, (iw, ih),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REFLECT_101
            )
           
            pt = np.array([cx, cy, 1.0])
            cx = float(np.dot(M[0], pt))
            cy = float(np.dot(M[1], pt))


    side = int(round(max(w, h) * margin_ratio))
    side = max(side, 120)

    x1 = int(round(cx - side / 2.0))
    y1 = int(round(cy - side / 2.0))
    x2 = x1 + side
    y2 = y1 + side

    # Tangani batas luar gambar dengan Border Reflection (mencegah dahi terpotong tanpa distorsi)
    pad_l = max(0, -x1)
    pad_t = max(0, -y1)
    pad_r = max(0, x2 - iw)
    pad_b = max(0, y2 - ih)

    if pad_l > 0 or pad_t > 0 or pad_r > 0 or pad_b > 0:
        padded = cv2.copyMakeBorder(
            aligned_img, pad_t, pad_b, pad_l, pad_r,
            cv2.BORDER_REFLECT_101
        )
        crop_np = padded[y1 + pad_t : y2 + pad_t, x1 + pad_l : x2 + pad_l]
    else:
        crop_np = aligned_img[y1:y2, x1:x2]

    if crop_np.size == 0 or crop_np.shape[0] < 10 or crop_np.shape[1] < 10:
        crop_np = cv2.resize(aligned_img, target_size)

    face_pil = Image.fromarray(crop_np).resize(target_size, Image.LANCZOS)
    face_arr = np.array(face_pil, dtype='float32')
    face_norm = (face_arr - 127.5) / 128.0
    return face_norm


def detect_and_crop_face(image_path, target_size=(160, 160), return_mirror=False, multi_margin=False):
    """
    Mendeteksi wajah menggunakan MTCNN dengan evaluasi rotasi cerdas (anti-180° inversion),
    eye alignment, padding simetris persegi (1:1) tanpa distorsi aspek rasio,
    dan normalisasi FaceNet standard.
    """
    try:
        img = Image.open(image_path).convert('RGB')
        # Fix EXIF orientation (penting untuk foto dari HP Android/iOS/Tablet)
        img = ImageOps.exif_transpose(img)
        img_rgb = np.array(img)
        ih, iw = img_rgb.shape[:2]

        # 1. Coba deteksi pada orientasi asli (0°)
        results_0 = detector.detect_faces(img_rgb)
        best_face_0 = _filter_best_real_face(results_0, min_size=50, require_upright=True)

        best_candidate = None
        # Jika orientasi 0° sudah memiliki wajah tegak yang jelas (conf >= 0.85), langsung gunakan!
        # JANGAN pernah merotasi jika di 0° sudah terdeteksi wajah tegak manusia.
        if best_face_0 and best_face_0['confidence'] >= 0.85:
            best_candidate = {
                'face': best_face_0,
                'image': img_rgb,
                'rotation': 0,
                'conf': best_face_0['confidence']
            }
        else:
            # 2. Hanya jika di 0° tidak ada wajah tegak yang meyakinkan, baru evaluasi rotasi lain
            candidates = []
            if best_face_0:
                candidates.append({
                    'face': best_face_0,
                    'image': img_rgb,
                    'rotation': 0,
                    'conf': best_face_0['confidence']
                })

            all_rotations = [
                (90, cv2.ROTATE_90_CLOCKWISE),
                (270, cv2.ROTATE_90_COUNTERCLOCKWISE),
                (180, cv2.ROTATE_180),
            ]

            for angle, rot_code in all_rotations:
                rot_img = cv2.rotate(img_rgb, rot_code)
                res = detector.detect_faces(rot_img)
                f = _filter_best_real_face(res, min_size=50, require_upright=True)
                if f and f['confidence'] >= 0.80:
                    candidates.append({
                        'face': f,
                        'image': rot_img,
                        'rotation': angle,
                        'conf': f['confidence']
                    })

            if candidates:
                # Prioritaskan rotasi 0° jika ada, kemudian confidence tertinggi
                candidates_0 = [c for c in candidates if c['rotation'] == 0]
                if candidates_0:
                    best_candidate = max(candidates_0, key=lambda c: c['conf'])
                else:
                    best_candidate = max(candidates, key=lambda c: c['conf'])
                    print(f"   🔄 [FaceNet] Terpilih rotasi tegak: {best_candidate['rotation']}° (conf: {best_candidate['conf']:.3f})")

        # 3. Jika wajah valid ditemukan:
        if best_candidate:
            best_face = best_candidate['face']
            active_rgb = best_candidate['image']
            detected_rot = best_candidate['rotation']
            x, y, w, h = best_face['box']
            conf = best_face['confidence']

            face_norm = align_and_square_crop(active_rgb, best_face, target_size=target_size, margin_ratio=1.35)
            face_tensor = np.expand_dims(face_norm, axis=0)

            print(f"   ✅ [FaceNet] MTCNN OK (rot: {detected_rot}°, conf: {conf:.3f}, box: [{x},{y},{w},{h}], 1:1 square crop)")

            if multi_margin:
                # Crop tighter (margin 1.15) untuk mencocokkan foto registrasi close-up
                tight_norm = align_and_square_crop(active_rgb, best_face, target_size=target_size, margin_ratio=1.15)
                tight_tensor = np.expand_dims(tight_norm, axis=0)
                return face_tensor, tight_tensor

            if return_mirror:
                face_flip_norm = np.fliplr(face_norm)
                face_flip_tensor = np.expand_dims(face_flip_norm, axis=0)
                return face_tensor, face_flip_tensor

            return face_tensor

        # 4. Fallback jika MTCNN gagal tapi gambar sudah berupa foto wajah pre-cropped
        aspect = iw / max(ih, 1)
        if 0.50 <= aspect <= 1.80 and min(iw, ih) >= 60:
            print(f"   ℹ️ [FaceNet] MTCNN no-face, fallback direct square crop ({iw}x{ih})")
            max_d = max(iw, ih)
            pad_w = (max_d - iw) // 2
            pad_h = (max_d - ih) // 2
            padded_img = cv2.copyMakeBorder(
                img_rgb, pad_h, max_d - ih - pad_h, pad_w, max_d - iw - pad_w,
                cv2.BORDER_REFLECT_101
            )
            face_pil = Image.fromarray(padded_img).resize(target_size, Image.LANCZOS)
            face_arr = np.array(face_pil, dtype='float32')
            face_norm = (face_arr - 127.5) / 128.0
            face_tensor = np.expand_dims(face_norm, axis=0)
            if multi_margin:
                return face_tensor, face_tensor
            if return_mirror:
                face_flip_norm = np.fliplr(face_norm)
                return face_tensor, np.expand_dims(face_flip_norm, axis=0)
            return face_tensor

        print(f"   ⚠️ [FaceNet] Tidak ada wajah valid terdeteksi di {os.path.basename(image_path)} (dim: {iw}x{ih})")
        return (None, None) if (return_mirror or multi_margin) else None

    except Exception as e:
        print(f"   ❌ Error saat deteksi wajah: {e}")
        return (None, None) if (return_mirror or multi_margin) else None


# ============================================
# EMBEDDING EXTRACTION
# ============================================
def get_embedding(image_path):
    """
    Mengekstrak embedding 512-dimensi dari wajah yang terdeteksi (single primary).
    Embedding selalu dinormalisasi L2 agar cosine similarity = dot product.
    """
    try:
        face = detect_and_crop_face(image_path, return_mirror=False)
        if face is None:
            print(f"   ⚠️ Tidak ada wajah terdeteksi di: {os.path.basename(image_path)}")
            return None
        embedding = model.predict(face, verbose=0)[0]
        norm = np.linalg.norm(embedding)
        if norm > 1e-9:
            embedding = embedding / norm
        return embedding
    except Exception as e:
        print(f"   ❌ Error extracting embedding: {e}")
        return None


def get_embeddings(image_path):
    """
    Mengekstrak embedding multi-margin & multi-mirror:
    - Standard square crop (margin 1.35) + mirror
    - Tight square crop (margin 1.15) + mirror
    Mengembalikan (primary_embedding, candidate_embeddings_list).
    Semua embedding dinormalisasi L2.
    """
    try:
        crops = detect_and_crop_face(image_path, multi_margin=True)
        if crops is None or crops[0] is None:
            print(f"   ⚠️ Tidak ada wajah terdeteksi di: {os.path.basename(image_path)}")
            return None, None
        face_std, face_tight = crops

        # 1. Standard crop & mirror
        emb_std = model.predict(face_std, verbose=0)[0]
        norm_std = np.linalg.norm(emb_std)
        if norm_std > 1e-9:
            emb_std = emb_std / norm_std

        face_std_flip = np.expand_dims(np.fliplr(face_std[0]), axis=0)
        emb_std_flip = model.predict(face_std_flip, verbose=0)[0]
        norm_sf = np.linalg.norm(emb_std_flip)
        if norm_sf > 1e-9:
            emb_std_flip = emb_std_flip / norm_sf

        # 2. Tight crop & mirror
        emb_tight = model.predict(face_tight, verbose=0)[0]
        norm_t = np.linalg.norm(emb_tight)
        if norm_t > 1e-9:
            emb_tight = emb_tight / norm_t

        face_tight_flip = np.expand_dims(np.fliplr(face_tight[0]), axis=0)
        emb_tight_flip = model.predict(face_tight_flip, verbose=0)[0]
        norm_tf = np.linalg.norm(emb_tight_flip)
        if norm_tf > 1e-9:
            emb_tight_flip = emb_tight_flip / norm_tf

        candidates = [emb_std, emb_std_flip, emb_tight, emb_tight_flip]
        return emb_std, candidates
    except Exception as e:
        print(f"   ❌ Error extracting embeddings: {e}")
        return None, None


# ============================================
# FACE COMPARISON (Cosine Similarity)
# ============================================
def compare_faces(test_embedding, known_embeddings, threshold=None, test_embedding_flipped=None):
    """
    Membandingkan embedding test dengan daftar embedding yang tersimpan.
    Mendukung input single vector, flipped vector, maupun candidate list multi-crop.
    Mengembalikan skor similarity tertinggi (0.0 - 1.0) dengan akurasi tinggi.
    """
    if test_embedding is None or not known_embeddings:
        return 0.0

    # Kumpulkan semua query candidate vectors
    query_vectors = []
    if isinstance(test_embedding, (list, tuple)):
        query_vectors.extend(test_embedding)
    elif isinstance(test_embedding, np.ndarray):
        query_vectors.append(test_embedding)

    if test_embedding_flipped is not None:
        if isinstance(test_embedding_flipped, (list, tuple)):
            query_vectors.extend(test_embedding_flipped)
        elif isinstance(test_embedding_flipped, np.ndarray):
            query_vectors.append(test_embedding_flipped)

    norm_queries = []
    for q in query_vectors:
        if q is not None and isinstance(q, np.ndarray):
            norm = np.linalg.norm(q)
            if norm > 1e-9:
                norm_queries.append(q / norm)

    if not norm_queries:
        return 0.0

    best_similarity = 0.0
    for emb in known_embeddings:
        if emb is None:
            continue
        norm_e = np.linalg.norm(emb)
        if norm_e < 1e-9:
            continue
        emb_norm = emb / norm_e

        for q in norm_queries:
            similarity = float(np.dot(q, emb_norm))
            if similarity > best_similarity:
                best_similarity = similarity

    return best_similarity


# ============================================
# HELPER: Read TXT metadata
# ============================================
def read_txt(data_path):
    """Membaca file metadata [NIP, Nama] dari file .txt."""
    with open(data_path, 'r', encoding='utf-8') as file:
        line = file.readline().strip().strip('[]')
        nip, name = line.split(', ')
    return nip, name


# ============================================
# HELPER: Validasi gambar
# ============================================
def is_valid_image(file_storage):
    """Memeriksa apakah file yang diupload adalah gambar valid."""
    try:
        image = Image.open(file_storage.stream)
        image.verify()
        file_storage.stream.seek(0)
        return True
    except Exception:
        return False


# ============================================
# REGISTRASI WAJAH + GENERATE EMBEDDING
# ============================================
def register_user_and_generate_embeddings(person_nip, person_name, image_files):
    """
    Menyimpan foto wajah dan menghasilkan embedding menggunakan
    pipeline MTCNN + FaceNet yang benar dengan square padding dan normalisasi L2.
    """
    curr_dir = os.getcwd()
    samples_dir = os.path.join(curr_dir, "samples")
    embeddings_dir = os.path.join(curr_dir, "samples_embedding")

    person_sample_path = os.path.join(samples_dir, person_nip)
    person_embedding_path = os.path.join(embeddings_dir, person_nip)

    os.makedirs(person_sample_path, exist_ok=True)
    os.makedirs(person_embedding_path, exist_ok=True)

    embeddings = []
    for i, image_file in enumerate(image_files):
        img_path = os.path.join(person_sample_path, f"{i}.jpg")
        image_file.save(img_path)
        embedding = get_embedding(img_path)
        if embedding is not None:
            embeddings.append(embedding)
            print(f"   ✅ Foto {i+1}: Wajah terdeteksi, embedding berhasil dibuat")
        else:
            print(f"   ⚠️ Foto {i+1}: Wajah TIDAK terdeteksi, dilewati")

    if embeddings:
        pkl_path = os.path.join(person_embedding_path, f"{person_nip}.pkl")
        txt_path = os.path.join(person_embedding_path, f"{person_nip}.txt")

        with open(pkl_path, "wb") as f:
            pickle.dump(embeddings, f)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(f"[{person_nip}, {person_name}]\n")

        print(f"   📦 {len(embeddings)}/{len(image_files)} embedding disimpan untuk {person_name}")
        return {"message": f"{len(embeddings)} embeddings saved for {person_nip} (MTCNN pipeline)"}, 200
    else:
        return {"error": "Tidak ada wajah yang terdeteksi di semua foto. Pastikan foto menampilkan wajah dengan jelas."}, 400


# ============================================
# EMBEDDING MIGRATION / REFRESH HELPER
# ============================================
def refresh_user_embeddings(nip):
    """
    Memperbarui file .pkl embedding untuk NIP tertentu langsung dari folder samples/<nip>.
    """
    curr_dir = os.getcwd()
    sample_folder = os.path.join(curr_dir, "samples", str(nip))
    emb_folder = os.path.join(curr_dir, "samples_embedding", str(nip))
    if not os.path.exists(sample_folder):
        return False

    img_files = [f for f in os.listdir(sample_folder) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    if not img_files:
        return False

    new_embeddings = []
    for fname in sorted(img_files):
        fpath = os.path.join(sample_folder, fname)
        emb = get_embedding(fpath)
        if emb is not None:
            new_embeddings.append(emb)

    if new_embeddings:
        os.makedirs(emb_folder, exist_ok=True)
        pkl_path = os.path.join(emb_folder, f"{nip}.pkl")
        with open(pkl_path, "wb") as f:
            pickle.dump(new_embeddings, f)
        print(f"   🔄 [REFRESH] Berhasil memperbarui {len(new_embeddings)} embedding untuk {nip}")
        return True
    return False


def _auto_refresh_active_users():
    """
    Sinkronisasi embedding dari folder samples/ ke samples_embedding/
    menggunakan pipeline square crop & L2 normalization terbaru.
    """
    try:
        curr_dir = os.getcwd()
        samples_dir = os.path.join(curr_dir, "samples")
        emb_dir = os.path.join(curr_dir, "samples_embedding")
        marker_file = os.path.join(emb_dir, ".v2_migrated")
        if os.path.exists(marker_file) or not os.path.exists(samples_dir):
            return

        print("🔄 [AUTO-SYNC] Memulai sinkronisasi embedding dengan pipeline v2...")
        user_dirs = [d for d in os.listdir(samples_dir) if os.path.isdir(os.path.join(samples_dir, d))]
        if "031188791093271576" in user_dirs:
            user_dirs.remove("031188791093271576")
            user_dirs.insert(0, "031188791093271576")

        for nip in user_dirs:
            try:
                refresh_user_embeddings(nip)
            except Exception as ue:
                print(f"⚠️ [AUTO-SYNC] Gagal update {nip}: {ue}")

        with open(marker_file, "w") as f:
            f.write("v2_all_users_migrated\n")
        print("✅ [AUTO-SYNC] Seluruh embedding berhasil dimigrasikan ke pipeline v2.")
    except Exception as e:
        print(f"⚠️ [AUTO-SYNC] Error refresh embedding: {e}")

# Jalankan auto refresh di background thread agar tidak menahan startup
threading.Thread(target=_auto_refresh_active_users, daemon=True).start()

