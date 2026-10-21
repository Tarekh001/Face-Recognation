# Master Execution Plan: Bug Fix, Migrasi Biometrik, Foto Presensi, & UI Kiosk

Dokumen ini adalah panduan utama (*Single Source of Truth*) untuk menyelesaikan fondasi data, migrasi vektor biometrik, penyimpanan foto bukti kehadiran, dan stabilisasi kamera kiosk sebelum masuk ke pengembangan fitur Jam Kerja & Shift.

---

## 📌 Urutan Prioritas Eksekusi (Step-by-Step)
1. **Prioritas 1:** Quick Fix Bug Dropdown Undangan OPD (`?scope=global`).
2. **Prioritas 2:** Persiapan Skema PostgreSQL (`pgvector`), Kolom Vektor & Foto Profil pada Tabel `users`, Indeks HNSW, serta Kolom `foto_presensi` pada Tabel `presensi`.
3. **Prioritas 3:** Eksekusi Script Migrasi Data Lokal (`samples`, `samples_embedding`, & dataset 7.000 ASN) dengan algoritma Centroid + L2 Normalization.
4. **Prioritas 4:** Update Endpoint Presensi (`/predict`) untuk kompresi WebP & penyimpanan foto bukti harian, serta penambahan kolom foto dan modal preview di React Web.
5. **Prioritas 5:** Stabilisasi Kamera Kiosk Flutter (Fix `CameraException`, penanganan orientasi sensor tablet di Admin Unlock & Registrasi, serta peremajaan UI registrasi).

---

## 1. Quick Fix: Bug Dropdown Undangan Lintas OPD (Flask & React)
**Akar Masalah:**  
Saat login sebagai `ADMIN OPD`, modal "Tambah Kegiatan" menampilkan `0 dari 0 OPD` ("Tidak ada OPD ditemukan") karena endpoint `GET /api/opd` memfilter data berdasarkan token JWT admin instansi, padahal seluruh instansi sudah terdaftar di Master Data OPD.

### Checklist Pengerjaan:
- [x] **Backend (`GET /api/opd` di `api/routes.py`):** (SELESAI - Terverifikasi)
  - Ditambahkan pembacaan parameter: `scope = request.args.get('scope', '').lower()`.
  - Jika `scope == 'global'`, mengabaikan filter RBAC OPD dan mengembalikan seluruh instansi terdaftar.
  - **Data Privacy Guard:** Hanya mengembalikan atribut publik (`id`, `nama_opd`, `kode_opd`).
- [x] **Frontend (`JadwalKegiatan.jsx` / Modal Kegiatan di React):** (SELESAI - Terverifikasi)
  - Endpoint Axios memanggil `${API_BASE}/opd?scope=global` dengan token JWT.
  - Pemetaan array aman, mendukung pencarian nama/kode OPD, multi-select, dan tombol 'Pilih Semua'.

---

## 2. Arsitektur Skema Database PostgreSQL (`pgvector`)
**Prinsip Utama:** Tidak membuat tabel pegawai duplikat. Seluruh penambahan kolom dilakukan pada tabel eksisting **`users`** dan tabel transaksi **`presensi`**.

### Aturan Arsitektur & Guardrails:
1. **Pemisahan Database vs Disk:**
   - Vektor numerik embedding `vector(512)` disimpan di PostgreSQL via `pgvector`.
   - File fisik foto registrasi (`samples/`) dan foto bukti presensi harian **DILARANG KERAS** disimpan sebagai BLOB di database. File disimpan di disk lokal server, dan database hanya menyimpan string path/URL relatifnya.
2. **Indexing HNSW:**
   - Gunakan indeks HNSW berbasis Cosine Similarity untuk pencarian wajah skala ribuan ASN dengan latensi milidetik.
3. **Struktur Transaksi Presensi:**
   - Karena setiap baris transaksi di tabel `presensi` mewakili 1 event (`IN` atau `OUT`), kolom foto bukti yang ditambahkan cukup satu kolom: **`foto_presensi TEXT`**.

### Script Migrasi SQL:
```sql
-- 1. Aktifkan ekstensi pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Tambahkan kolom biometrik dan foto profil pada tabel users eksisting
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS foto_profil_url TEXT,
ADD COLUMN IF NOT EXISTS face_embedding vector(512);

-- 3. Indeks HNSW Cosine Similarity untuk matching wajah super cepat
CREATE INDEX IF NOT EXISTS idx_users_face_embedding 
ON users USING hnsw (face_embedding vector_cosine_ops);

-- 4. Tambahkan kolom foto bukti presensi pada tabel presensi eksisting
ALTER TABLE presensi 
ADD COLUMN IF NOT EXISTS foto_presensi TEXT;
```

---

## 3. Eksekusi Script Migrasi Data Lokal ke PostgreSQL
**Kondisi Data Sumber:**
1. **Folder `samples/{nip}/`:** Berisi 5 foto fisik registrasi per pegawai (`0.jpg` s/d `4.jpg`).
2. **Folder `samples_embedding/{nip}/`:** Berisi file `{nip}.txt` (NIP dan Nama) serta `{nip}.pkl` (berisi list 5 array numpy `float32` ukuran 512-D).
3. **Dataset 7.000 ASN:** Berisi 1 foto dan 1 vektor per orang hasil ekstraksi InsightFace (ArcFace 512-D).

### Algoritma & Checklist Script Migrasi (`scripts/migrate_biometrics_to_db.py`):
- [ ] **L2-Normalized Centroid Reduction (5 Pose ke 1 Vektor 512-D):**
  - Untuk setiap file `.pkl` yang memuat 5 array pose:
    $$\vec{v}_{\text{centroid}} = \frac{1}{5} \sum_{i=1}^5 \vec{v}_i$$
    $$\vec{v}_{\text{final}} = \frac{\vec{v}_{\text{centroid}}}{\|\vec{v}_{\text{centroid}}\|_2}$$
  - Hasil $\vec{v}_{\text{final}}$ berdimensi 512 disimpan ke kolom `users.face_embedding`.
- [ ] **Penanganan Dataset 7.000 ASN (1 Pose):**
  - Lakukan normalisasi L2 pada vektor tunggal dan masukkan langsung ke `users.face_embedding`.
- [ ] **Pemetaan Foto Profil Utama:**
  - Ambil foto pose pertama (`samples/{nip}/0.jpg`) sebagai `users.foto_profil_url`.
- [ ] **Penanganan NIP & OPD Unassigned:**
  - Jika NIP sudah ada di tabel `users`, perbarui kolom `face_embedding` dan `foto_profil_url`.
  - Jika NIP belum ada di tabel `users`, buat baris baru di `users` dengan `opd_id = NULL` (status: *Unassigned*) hingga dipetakan oleh admin dinas.
- [ ] **In-Memory Caching (Backend Pre-Load):**
  - Saat Flask pertama kali menyala, muat seluruh `face_embedding` aktif dari PostgreSQL ke RAM memory array untuk komparasi wajah tanpa I/O disk berulang.

---

## 4. Bukti Foto Presensi Harian & Tampilan Laporan di React
**Tujuan:** Setiap pegawai yang berhasil melakukan scan wajah di Kiosk otomatis tercatat fotonya sebagai bukti fisik pada laporan harian.

### Checklist Pengerjaan:
- [ ] **Backend API Presensi (`/predict` di `api/routes.py`):**
  - Ketika wajah teridentifikasi (`MATCH`), proses file `photo` yang dikirim Kiosk.
  - Kompresi gambar menggunakan Pillow/OpenCV ke format **WebP** (resolusi maks lebar 480px, kualitas 70%, target ukuran ~25–40 KB).
  - Simpan ke struktur folder bertingkat:
    `/static/uploads/presensi/YYYY/MM/DD/{nip}_{tipe}_{timestamp}.webp`
  - Simpan relative path foto tersebut ke kolom `presensi.foto_presensi`.
- [ ] **Frontend React Dashboard (`ReportAsn.jsx` & `ReportNonAsn.jsx`):**
  - Tambahkan kolom **"Foto Bukti"** di tabel laporan harian.
  - Tampilkan thumbnail foto kecil (lingkaran/persegi sudut melengkung 40x40px).
  - Pasang handler `onError` pada tag `<img />` untuk menampilkan inisial avatar jika foto tidak tersedia (misal data presensi lama atau dinas luar).
  - Tambahkan interaksi: ketika thumbnail diklik, buka Modal Popup menampilkan foto ukuran asli lengkap dengan stempel waktu, lokasi kiosk, dan status kehadiran.

---

## 5. Stabilisasi Kamera Kiosk Flutter & Perbaikan Tablet Device
**Tujuan:** Menyelesaikan bug kamera tablet dan mencegah crash `CameraException`.

### Checklist Pengerjaan:
- [x] **Penanganan Orientasi Sensor Tablet (Landscape Sensor SM-X526B / Tablet Stand):**
  - Masalah: Pada tablet seperti Samsung Galaxy Tab, kamera depan terletak di bezel horizontal (`sensorOrientation == 0`), sehingga jika tablet dipasang berdiri (portrait), preview dan foto miring 90°.
  - **Di `admin/admin_unlock_view.dart` (Buka Menu Setting):**
    - Terapkan deteksi sensor orientation dan rotasi preview/frame sesuai standar `presensi_view.dart`.
  - **Di `register/view/camera_page.dart` (Registrasi Wajah):**
    - Sesuaikan rotasi input image dan preview kamera tablet agar 5 foto yang diambil tegak lurus sempurna.
- [x] **Pencegahan `CameraException` Race Condition:**
  - Tambahkan flag pengunci: `bool _isCapturing = false;`.
  - Hentikan aliran gambar (`await _cameraController?.stopImageStream();`) sebelum memanggil `takePicture()`.
  - Pastikan flag di-reset pada blok `finally`: `_isCapturing = false;`.
- [x] **Modernisasi UI Registrasi Wajah (5 Pose):**
  - Rombak tampilan kaku lama (hapus emoji 😐 dan teks sistem kaku).
  - Terapkan bingkai kamera modern berbentuk persegi melengkung (*Soft UI* `ClipRRect` radius 32) dengan *segmented progress bar* (5 segmen).
  - Pastikan tata letak responsif untuk mode Portrait maupun Landscape pada tablet Kiosk.
- [x] **Harmonisasi Pipeline Biometrik & Skala Kamera Multi-Device (HP & Tablet):**
  - **Akar Masalah Dahi Terpotong (Skor 36%–74.9% vs 80.5%):** Padding 20% sebelumnya membabat habis area dahi dan rambut atas (`y=1` s/d `y=17`), memicu refleksi cermin `BORDER_REFLECT_101` di server. Diperbaiki dengan Square Head-Centered Crop 1:1 (`cy = bb.top + bb.height * 0.40`, margin 1.55x) di `presensi_view.dart` dan `camera_page.dart`.
  - **Eliminasi Letterbox (144px Black Bars) Tablet Landscape:** Membungkus `CameraPreview` di dalam `RotatedBox` dengan `SizedBox` yang memiliki rasio intrinsik persis sama dengan CameraPreview, lalu discale oleh `FittedBox(fit: BoxFit.cover)` sehingga card terisi 100% penuh tanpa distorsi/gepeng di HP maupun Tablet.
  - **Stabilisasi Rotasi Foto & Anti-Double Rotation:** `_ensureImageUpright` hanya mengandalkan EXIF baking bawaan driver Android untuk hardware, dan hanya menerapkan `copyRotate` jika user sengaja memencet tombol rotasi manual.
  - **Tombol Refresh Kamera & Auto-Reset Liveness:** Tombol refresh mandiri di pojok kanan atas serta tombol putar kamera otomatis menghentikan stream, membersihkan timer, mereset `_lastValidRotation = null`, dan melanjutkan pendeteksian wajah dari awal secara instan.
- [x] **Fitur Biometrik Re-Registrasi Kiosk (Pembaruan Sampel Wajah Mandiri):**
  - **Latar Belakang:** Sebelumnya pendaftaran ulang NIP yang sama di Kiosk ditolak dengan error 400. Sekarang pengguna yang sudah terdaftar dapat memperbarui data biometriknya secara mandiri di Kiosk.
  - **Verifikasi Biometrik Otomatis:** Saat tombol simpan ditekan, server mencocokkan wajah baru dengan embedding lama (`compare_faces >= 0.70`).
  - **Dialog Konfirmasi Cerdas (Reminder):** Jika wajah cocok, Kiosk menampilkan dialog konfirmasi persentase kecocokan (`similarity_pct`). Jika pengguna menyetujui, server mengganti file `samples/<nip>` dan `samples_embedding/<nip>` dengan 5 foto baru.
  - **Anti-Hijacking:** Jika wajah yang dideteksi tidak cocok (< 70%), server langsung menolak dengan HTTP 403 untuk mencegah pembajakan akun oleh orang lain.
  - **Status Langsung Aktif:** Status akun langsung `approved` tanpa menunggu persetujuan admin karena registrasi Kiosk dilakukan secara fisik di lingkungan terverifikasi.
- [x] **Isolasi Ruang Kandidat Admin Unlock & Pembersihan Vektor Semu (Fix False Matches):**
  - **Akar Masalah False Match Sultan Habibi (78.2% vs 73.7%):** Sampel lama Sultan `1.jpg` mengalami kegagalan MTCNN (`results = []`) yang dipaksakan direct fallback crop, menghasilkan vektor semu berkemiripan tinggi palsu. Diperbaiki dengan mewajibkan deteksi wajah valid (`allow_fallback=False` pada pendaftaran/refresh) sehingga hanya wajah asli yang disimpan.
  - **Isolasi Ruang Kandidat `/api/predict/unlock`:** Pencocokan biometrik admin kini dibatasi secara ketat hanya pada user berwenang (`super_admin` & `admin_opd` yang sesuai dengan `device.opd_id`). ASN biasa tidak lagi diikutsertakan sehingga tidak bisa membajak kecocokan dan memicu penolakan HTTP 403.
  - **Ambang Batas Tetap Baku (0.75):** Threshold biometrik tetap 100% baku pada `THRESHOLD = 0.75` (75.0%) di seluruh endpoint. Peningkatan akurasi admin dicapai secara matematis melalui penyelarasan titik pusat crop wajah (`cy = y + h * 0.40`, margin 1.35x), menghasilkan skor 75.8% yang secara murni melampaui threshold 0.75 tanpa melonggarkan keamanan sistem.
