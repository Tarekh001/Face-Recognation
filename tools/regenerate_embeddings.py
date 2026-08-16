"""
============================================================
SCRIPT: Regenerasi Semua Embedding dengan Pipeline MTCNN
============================================================
Jalankan script ini SATU KALI setelah update facenet_utils.py
untuk menghasilkan ulang semua embedding dari foto registrasi
yang sudah ada di folder 'samples/'.

Perintah:
    python regenerate_embeddings.py

Catatan:
    - Script ini akan MENIMPA semua file .pkl di samples_embedding/
    - File .txt (metadata NIP/Nama) TIDAK akan diubah
    - Foto asli di samples/ TIDAK akan diubah
============================================================
"""

import os
import sys
import pickle
import time
import numpy as np

# Setup path agar bisa import dari api/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.facenet_utils import get_embedding, detector

def regenerate_all_embeddings():
    curr_dir = os.getcwd()
    samples_dir = os.path.join(curr_dir, "samples")
    embeddings_dir = os.path.join(curr_dir, "samples_embedding")

    if not os.path.exists(samples_dir):
        print("❌ Folder 'samples/' tidak ditemukan!")
        return

    # Hitung total
    all_persons = [d for d in os.listdir(samples_dir) if os.path.isdir(os.path.join(samples_dir, d))]
    total_persons = len(all_persons)

    print("=" * 60)
    print("🔄 REGENERASI EMBEDDING DENGAN PIPELINE MTCNN + FACENET")
    print("=" * 60)
    print(f"📂 Folder samples   : {samples_dir}")
    print(f"📂 Folder embeddings: {embeddings_dir}")
    print(f"👥 Total ASN         : {total_persons}")
    print("=" * 60)

    success_count = 0
    fail_count = 0
    skipped_count = 0
    start_time = time.time()

    for idx, person_nip in enumerate(all_persons, 1):
        person_sample_path = os.path.join(samples_dir, person_nip)
        person_embedding_path = os.path.join(embeddings_dir, person_nip)

        # Cari semua file gambar
        image_files = [
            f for f in os.listdir(person_sample_path)
            if f.lower().endswith(('.jpg', '.jpeg', '.png'))
        ]

        if not image_files:
            print(f"  [{idx}/{total_persons}] ⚠️ {person_nip}: Tidak ada foto, dilewati")
            skipped_count += 1
            continue

        # Baca metadata dari .txt yang sudah ada
        txt_path = os.path.join(person_embedding_path, f"{person_nip}.txt")
        person_name = person_nip  # default
        if os.path.exists(txt_path):
            try:
                with open(txt_path, 'r') as f:
                    line = f.readline().strip().strip('[]')
                    _, person_name = line.split(', ')
            except Exception:
                pass

        print(f"\n  [{idx}/{total_persons}] 🔄 Processing: {person_name} (NIP: {person_nip})")
        print(f"             📷 {len(image_files)} foto ditemukan")

        # Generate embedding untuk setiap foto
        embeddings = []
        for img_file in sorted(image_files):
            img_path = os.path.join(person_sample_path, img_file)
            embedding = get_embedding(img_path)
            if embedding is not None:
                embeddings.append(embedding)
                print(f"             ✅ {img_file}: Wajah terdeteksi")
            else:
                print(f"             ❌ {img_file}: Wajah TIDAK terdeteksi")

        if embeddings:
            # Pastikan folder embedding ada
            os.makedirs(person_embedding_path, exist_ok=True)

            # Simpan embedding baru (Overwrite .pkl lama)
            pkl_path = os.path.join(person_embedding_path, f"{person_nip}.pkl")
            with open(pkl_path, "wb") as f:
                pickle.dump(embeddings, f)

            # Pastikan .txt ada (jika belum)
            if not os.path.exists(txt_path):
                with open(txt_path, "w") as f:
                    f.write(f"[{person_nip}, {person_name}]\n")

            print(f"             📦 {len(embeddings)}/{len(image_files)} embedding disimpan ✅")
            success_count += 1
        else:
            print(f"             ❌ GAGAL: Tidak ada wajah terdeteksi di semua foto!")
            fail_count += 1

    # Summary
    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("📊 HASIL REGENERASI EMBEDDING")
    print("=" * 60)
    print(f"  ✅ Berhasil     : {success_count}/{total_persons}")
    print(f"  ❌ Gagal         : {fail_count}/{total_persons}")
    print(f"  ⚠️ Dilewati     : {skipped_count}/{total_persons}")
    print(f"  ⏱️ Waktu total  : {elapsed:.1f} detik")
    print("=" * 60)

    if fail_count > 0:
        print(f"\n⚠️ Ada {fail_count} ASN yang gagal. Periksa kualitas foto registrasi mereka.")
        print("   Pastikan foto menampilkan wajah dengan jelas, tidak blur, dan cukup terang.")

    if success_count > 0:
        print(f"\n✅ Regenerasi selesai! {success_count} ASN siap untuk face recognition.")
        print("   Anda bisa restart Flask server dan test scan wajah sekarang.")


if __name__ == "__main__":
    regenerate_all_embeddings()
