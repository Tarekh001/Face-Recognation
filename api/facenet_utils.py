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
# FACE DETECTION & ALIGNMENT (MTCNN)
# ============================================
def detect_and_crop_face(image_path, target_size=(160, 160)):
    """
    Mendeteksi wajah menggunakan MTCNN dengan multi-rotation fallback (0°, 90°, 270°, 180°),
    crop area wajah dengan padding 20%, lalu resize ke ukuran yang dibutuhkan FaceNet (160x160).
    Jika MTCNN tidak menemukan landmark pada foto yang sudah di-crop,
    menggunakan fallback pre-crop resize langsung agar tidak menghasilkan error 500.
    """
    try:
        img = Image.open(image_path).convert('RGB')
        # Fix EXIF orientation (penting untuk foto dari HP Android/iOS/Tablet)
        img = ImageOps.exif_transpose(img)
        img_rgb = np.array(img)

        # 1. Coba deteksi orientasi asli (0°)
        results = detector.detect_faces(img_rgb)
        active_rgb = img_rgb
        detected_rot = 0

        # 2. Multi-rotation fallback jika di 0° tidak ada wajah (kamera tablet / sensor landscape)
        if not results:
            rotations = [
                (cv2.ROTATE_90_CLOCKWISE, 90),
                (cv2.ROTATE_90_COUNTERCLOCKWISE, 270),
                (cv2.ROTATE_180, 180),
            ]
            for rot_code, angle in rotations:
                cand_rgb = cv2.rotate(img_rgb, rot_code)
                cand_results = detector.detect_faces(cand_rgb)
                if cand_results:
                    results = cand_results
                    active_rgb = cand_rgb
                    detected_rot = angle
                    print(f"   🔄 [FaceNet] Wajah terdeteksi via rotasi fallback: {angle}°")
                    break

        # 3. Jika MTCNN berhasil menemukan wajah:
        if results:
            best_face = max(results, key=lambda x: x['confidence'])
            x, y, w, h = best_face['box']
            conf = best_face['confidence']

            # Padding 20% proporsional untuk margin (agar fitur lengkap masuk ke FaceNet)
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
                face_array = (face_array - 127.5) / 128.0
                print(f"   ✅ [FaceNet] MTCNN OK (rot: {detected_rot}°, conf: {conf:.3f}, box: [{x},{y},{w},{h}])")
                return np.expand_dims(face_array, axis=0)

        # 4. Fallback jika MTCNN gagal tapi gambar sudah berupa foto wajah pre-cropped
        ih, iw = img_rgb.shape[:2]
        aspect = iw / max(ih, 1)
        if 0.60 <= aspect <= 1.60 and min(iw, ih) >= 80:
            print(f"   ℹ️ [FaceNet] MTCNN no-landmark, fallback direct crop ({iw}x{ih})")
            face_crop = img.resize(target_size, Image.LANCZOS)
            face_array = np.array(face_crop, dtype='float32')
            face_array = (face_array - 127.5) / 128.0
            return np.expand_dims(face_array, axis=0)

        print(f"   ⚠️ [FaceNet] Tidak ada wajah terdeteksi di {os.path.basename(image_path)} (dim: {iw}x{ih})")
        return None

    except Exception as e:
        print(f"   ❌ Error saat deteksi wajah: {e}")
        return None


# ============================================
# EMBEDDING EXTRACTION
# ============================================
def get_embedding(image_path):
    """
    Mengekstrak embedding 512-dimensi dari wajah yang terdeteksi.
    Pipeline: Load → MTCNN Detect → Crop → Normalize → FaceNet Predict
    """
    try:
        face = detect_and_crop_face(image_path)
        if face is None:
            print(f"   ⚠️ Tidak ada wajah terdeteksi di: {os.path.basename(image_path)}")
            return None
        embedding = model.predict(face, verbose=0)[0]
        return embedding
    except Exception as e:
        print(f"   ❌ Error extracting embedding: {e}")
        return None


# ============================================
# FACE COMPARISON (Cosine Similarity)
# ============================================
def compare_faces(test_embedding, known_embeddings, threshold):
    """
    Membandingkan embedding test dengan daftar embedding yang tersimpan.
    Mengembalikan skor similarity tertinggi (0.0 - 1.0).
    """
    best_similarity = 0.0
    for emb in known_embeddings:
        similarity = 1 - cosine(test_embedding, emb)
        if similarity > best_similarity:
            best_similarity = similarity
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
