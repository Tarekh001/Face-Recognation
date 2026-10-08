import os
import cv2
import numpy as np
import pickle
from keras_facenet import FaceNet
from mtcnn import MTCNN
from PIL import Image, ImageOps
from scipy.spatial.distance import cosine

# ============================================
# INISIALISASI MODEL (Satu kali saat startup)
# ============================================
facenet = FaceNet()
model = facenet.model
detector = MTCNN()

print("✅ [INIT] FaceNet + MTCNN Face Detector berhasil dimuat.")

# ============================================
# ============================================
# FACE DETECTION & ALIGNMENT (MTCNN)
# ============================================
def _filter_best_real_face(results, min_size=55):
    """
    Menyaring deteksi wajah MTCNN untuk mengabaikan noise/speck kecil (< min_size px).
    Wajah asli manusia pada foto presensi/selfie selalu berukuran minimal 55x55 px.
    Mengembalikan wajah dengan luas area terbesar dan confidence tertinggi.
    """
    if not results:
        return None
    valid = [f for f in results if f['box'][2] >= min_size and f['box'][3] >= min_size]
    if not valid:
        return None
    return max(valid, key=lambda f: (f['box'][2] * f['box'][3], f['confidence']))


def detect_and_crop_face(image_path, target_size=(160, 160), return_mirror=False):
    """
    Mendeteksi wajah menggunakan MTCNN dengan multi-rotation evaluation (0°, 90°, 180°, 270°),
    mengabaikan noise/speck kecil (< 55 px), crop area wajah dengan padding 20%,
    lalu resize ke ukuran yang dibutuhkan FaceNet (160x160).
    Jika return_mirror=True, mengembalikan tuple (face_tensor, face_mirror_tensor).
    """
    try:
        img = Image.open(image_path).convert('RGB')
        # Fix EXIF orientation (penting untuk foto dari HP Android/iOS/Tablet)
        img = ImageOps.exif_transpose(img)
        img_rgb = np.array(img)

        # 1. Coba deteksi pada orientasi asli (0°)
        results_0 = detector.detect_faces(img_rgb)
        best_face_0 = _filter_best_real_face(results_0, min_size=70)

        best_candidate = None
        # Jika orientasi 0° sudah memiliki wajah besar yang jelas (min 90px & conf >= 0.95), langsung gunakan
        if best_face_0 and min(best_face_0['box'][2], best_face_0['box'][3]) >= 90 and best_face_0['confidence'] >= 0.95:
            best_candidate = {
                'face': best_face_0,
                'image': img_rgb,
                'rotation': 0,
                'area': best_face_0['box'][2] * best_face_0['box'][3],
                'conf': best_face_0['confidence']
            }
        else:
            # 2. Evaluasi semua rotasi untuk mencari wajah manusia asli terbesar (anti-speck)
            all_rotations = [
                (0, None, results_0),
                (90, cv2.ROTATE_90_CLOCKWISE, None),
                (180, cv2.ROTATE_180, None),
                (270, cv2.ROTATE_90_COUNTERCLOCKWISE, None),
            ]

            candidates = []
            for angle, rot_code, pre_results in all_rotations:
                if rot_code is None:
                    rot_img = img_rgb
                    res = pre_results if pre_results is not None else detector.detect_faces(rot_img)
                else:
                    rot_img = cv2.rotate(img_rgb, rot_code)
                    res = detector.detect_faces(rot_img)

                f = _filter_best_real_face(res, min_size=55)
                if f:
                    area = f['box'][2] * f['box'][3]
                    candidates.append({
                        'face': f,
                        'image': rot_img,
                        'rotation': angle,
                        'area': area,
                        'conf': f['confidence']
                    })

            if candidates:
                # Pilih rotasi yang menghasilkan wajah terbesar & paling percaya diri
                best_candidate = max(candidates, key=lambda c: (c['area'], c['conf']))
                if best_candidate['rotation'] != 0:
                    print(f"   🔄 [FaceNet] Terpilih rotasi optimal: {best_candidate['rotation']}° (area: {best_candidate['area']} px²)")

        # 3. Jika wajah valid ditemukan:
        if best_candidate:
            best_face = best_candidate['face']
            active_rgb = best_candidate['image']
            detected_rot = best_candidate['rotation']
            x, y, w, h = best_face['box']
            conf = best_face['confidence']

            # Padding 20% proporsional untuk margin
            pad_w = int(w * 0.20)
            pad_h = int(h * 0.20)
            ih, iw = active_rgb.shape[:2]
            x1 = max(0, x - pad_w)
            y1 = max(0, y - pad_h)
            x2 = min(iw, x + w + pad_w)
            y2 = min(ih, y + h + pad_h)

            crop_np = active_rgb[y1:y2, x1:x2]
            if crop_np.size > 0:
                face_crop = Image.fromarray(crop_np).resize(target_size, Image.LANCZOS)
                face_array = np.array(face_crop, dtype='float32')
                face_norm = (face_array - 127.5) / 128.0
                face_tensor = np.expand_dims(face_norm, axis=0)

                print(f"   ✅ [FaceNet] MTCNN OK (rot: {detected_rot}°, conf: {conf:.3f}, box: [{x},{y},{w},{h}])")

                if return_mirror:
                    # Buat versi horizontal flip (mirror) untuk mengatasi perbedaan selfie camera mirror
                    face_flip_norm = np.fliplr(face_norm)
                    face_flip_tensor = np.expand_dims(face_flip_norm, axis=0)
                    return face_tensor, face_flip_tensor

                return face_tensor

        # 4. Fallback jika MTCNN gagal tapi gambar sudah berupa foto wajah pre-cropped
        ih, iw = img_rgb.shape[:2]
        aspect = iw / max(ih, 1)
        if 0.60 <= aspect <= 1.60 and min(iw, ih) >= 80:
            print(f"   ℹ️ [FaceNet] MTCNN no-landmark, fallback direct crop ({iw}x{ih})")
            face_crop = img.resize(target_size, Image.LANCZOS)
            face_array = np.array(face_crop, dtype='float32')
            face_norm = (face_array - 127.5) / 128.0
            face_tensor = np.expand_dims(face_norm, axis=0)
            if return_mirror:
                face_flip_norm = np.fliplr(face_norm)
                return face_tensor, np.expand_dims(face_flip_norm, axis=0)
            return face_tensor

        print(f"   ⚠️ [FaceNet] Tidak ada wajah valid terdeteksi di {os.path.basename(image_path)} (dim: {iw}x{ih})")
        return (None, None) if return_mirror else None

    except Exception as e:
        print(f"   ❌ Error saat deteksi wajah: {e}")
        return (None, None) if return_mirror else None


# ============================================
# EMBEDDING EXTRACTION
# ============================================
def get_embedding(image_path):
    """
    Mengekstrak embedding 512-dimensi dari wajah yang terdeteksi (single primary).
    Pipeline: Load → MTCNN Detect → Crop → Normalize → FaceNet Predict
    """
    try:
        face = detect_and_crop_face(image_path, return_mirror=False)
        if face is None:
            print(f"   ⚠️ Tidak ada wajah terdeteksi di: {os.path.basename(image_path)}")
            return None
        embedding = model.predict(face, verbose=0)[0]
        return embedding
    except Exception as e:
        print(f"   ❌ Error extracting embedding: {e}")
        return None


def get_embeddings(image_path):
    """
    Mengekstrak embedding wajah primer dan versi mirror (horizontal flip).
    Mengembalikan (embedding_primer, embedding_mirror).
    """
    try:
        face, face_flip = detect_and_crop_face(image_path, return_mirror=True)
        if face is None:
            print(f"   ⚠️ Tidak ada wajah terdeteksi di: {os.path.basename(image_path)}")
            return None, None
        emb = model.predict(face, verbose=0)[0]
        emb_flip = model.predict(face_flip, verbose=0)[0]
        return emb, emb_flip
    except Exception as e:
        print(f"   ❌ Error extracting embeddings: {e}")
        return None, None


# ============================================
# FACE COMPARISON (Cosine Similarity)
# ============================================
def compare_faces(test_embedding, known_embeddings, threshold, test_embedding_flipped=None):
    """
    Membandingkan embedding test dengan daftar embedding yang tersimpan.
    Jika test_embedding_flipped disediakan, juga membandingkan versi mirror
    dan mengambil nilai similarity tertinggi (mengatasi kamera selfie mirror).
    Mengembalikan skor similarity tertinggi (0.0 - 1.0).
    """
    best_similarity = 0.0
    for emb in known_embeddings:
        similarity = 1 - cosine(test_embedding, emb)
        if similarity > best_similarity:
            best_similarity = similarity
        if test_embedding_flipped is not None:
            sim_flip = 1 - cosine(test_embedding_flipped, emb)
            if sim_flip > best_similarity:
                best_similarity = sim_flip
    return best_similarity


# ============================================
# HELPER: Read TXT metadata
# ============================================
def read_txt(data_path):
    """Membaca file metadata [NIP, Nama] dari file .txt."""
    with open(data_path, 'r') as file:
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
    pipeline MTCNN + FaceNet yang benar.
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
        with open(txt_path, "w") as f:
            f.write(f"[{person_nip}, {person_name}]\n")

        print(f"   📦 {len(embeddings)}/{len(image_files)} embedding disimpan untuk {person_name}")
        return {"message": f"{len(embeddings)} embeddings saved for {person_nip} (MTCNN pipeline)"}, 200
    else:
        return {"error": "Tidak ada wajah yang terdeteksi di semua foto. Pastikan foto menampilkan wajah dengan jelas."}, 400
