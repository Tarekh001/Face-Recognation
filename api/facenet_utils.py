import os
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
    Mendeteksi wajah menggunakan MTCNN, crop area wajah,
    lalu resize ke ukuran yang dibutuhkan FaceNet (160x160).
    Mengembalikan numpy array siap prediksi, atau None jika tidak ada wajah.
    """
    try:
        img = Image.open(image_path).convert('RGB')
        # Fix EXIF orientation (penting untuk foto dari HP Android/iOS)
        img = ImageOps.exif_transpose(img)
        img_array = np.array(img)

        # Deteksi semua wajah di gambar
        results = detector.detect_faces(img_array)

        if not results:
            return None  # Tidak ada wajah terdeteksi

        # Ambil wajah dengan confidence tertinggi
        best_face = max(results, key=lambda x: x['confidence'])
        x, y, w, h = best_face['box']

        # Padding 15% untuk margin agar tidak terlalu tight crop
        pad_w = int(w * 0.15)
        pad_h = int(h * 0.15)
        x1 = max(0, x - pad_w)
        y1 = max(0, y - pad_h)
        x2 = min(img_array.shape[1], x + w + pad_w)
        y2 = min(img_array.shape[0], y + h + pad_h)

        # Crop wajah dari gambar asli
        face_crop = img.crop((x1, y1, x2, y2))
        face_crop = face_crop.resize(target_size, Image.LANCZOS)

        # Normalisasi pixel untuk FaceNet (standar: (pixel - 127.5) / 128.0)
        face_array = np.array(face_crop, dtype='float32')
        face_array = (face_array - 127.5) / 128.0

        return np.expand_dims(face_array, axis=0)

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
