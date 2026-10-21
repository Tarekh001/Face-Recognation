# Blueprint & Rencana Kerja: Modul Manajemen Jam Kerja & Sistem Shift

Dokumen ini adalah acuan arsitektur dan pengembangan fitur Multi-Jam Kerja dan Sistem Roster (*Shift*) untuk seluruh Perangkat Daerah (OPD) di lingkungan Pemerintah Kabupaten Tangerang.

> **Catatan Alur Kerja:** Modul ini diimplementasikan setelah tahapan fondasi database, migrasi data, dan perbaikan kamera Kiosk pada `TODO_MASTER.md` selesai dieksekusi.

---

## 1. Proses Bisnis & Pembagian Wewenang
* **Hierarki Wewenang Pengguna:**
  1. **Super Admin:** 
     - Mengelola Master Profil Jam Kerja (CRUD): membuat, mengubah, dan menghapus jenis jam kerja (contoh: *Reguler ASN*, *Shift Pagi*, *Shift Siang*, *Shift Malam*, *Jam Ramadan*).
     - Dapat menetapkan apakah profil jam kerja bersifat **Global** (berlaku untuk seluruh OPD) atau **Khusus OPD Tertentu** (misal: shift medis khusus RSUD/Dinkes, shift pengamanan khusus Satpol PP/BPBD).
  2. **Admin OPD (Dinas, Badan, Sekretariat, Kecamatan):**
     - Memilih dan menetapkan jam kerja untuk masing-masing pegawai di instansinya.
     - Melakukan penyusunan jadwal bergulir (*Plotting Roster*) bulanan/mingguan untuk pegawai dengan sistem shift.
     - Menangani perubahan jadwal mendadak (*Tukar Jaga* antar pegawai).
* **Cakupan Pegawai:**
  - Berlaku setara untuk seluruh pegawai **ASN** maupun **Non-ASN** di lingkungan Pemerintah Kabupaten Tangerang.

---

## 2. Core System Rules (5 Antisipasi Celah Masalah Shift di Backend)
Seluruh logika pemrosesan absensi pada API Flask (`/predict`) dan modul laporan (`/report`) wajib mematuhi 5 aturan inti:

### Rule 1: Cut-Off Lupa Absen Pulang (Missing Check-Out)
- Setiap profil jam kerja memiliki batas akhir scan pulang (`akhir_scan_pulang`).
- Jika pegawai tidak memindai wajah hingga melewati batas *cut-off*, sesi absensi hari itu otomatis ditutup dengan status **"Tidak Absen Pulang" (MISSING_OUT)**.
- **Tujuan:** Menjamin pemindaian keesokan harinya murni dibaca sebagai absen masuk (IN), bukan salah dibaca sebagai absen pulang yang tertunda.

### Rule 2: Overnight Paradox & Tanggal Penugasan (Shift Malam Lintas Hari)
- Shift malam yang melewati tengah malam (misal pukul 21:00 s/d 06:00 keesokan harinya) memiliki penanda `is_lintas_hari = True`.
- Pemindaian pulang pada pukul 06:00 pagi di hari berikutnya dicatat dengan **`tanggal_tugas` hari sebelumnya**.
- Backend menggunakan jendela waktu (`mulai_scan_masuk` s/d `akhir_scan_masuk`) untuk membedakan antara pegawai shift malam yang baru pulang dengan pegawai shift pagi yang baru datang di Kiosk yang sama.

### Rule 3: Toleransi Keterlambatan Terpusat (Grace Period)
- Penentuan status *"Tepat Waktu"* (`ON_TIME`) vs *"Terlambat"* (`LATE`) beserta jumlah menit keterlambatan (`keterlambatan_menit`) dihitung secara mutlak di backend.
- Perhitungan mengacu pada `batas_masuk = jam_masuk + menit_toleransi` dari profil jam kerja yang sedang dijalani pegawai pada tanggal tersebut.

### Rule 4: Hierarki Jadwal Kegiatan (Override Dinas Luar)
- Jika seorang pegawai tercatat hadir pada modul **Jadwal Kegiatan** (rapat lintas instansi atau penugasan luar), kehadirannya otomatis mengabaikan (*override*) kewajiban presensi di Kiosk instansi asalnya pada hari tersebut. Pegawai tidak akan dicatat alpa.

### Rule 5: Pengecualian Libur Nasional & Relokasi Validasi Server
- Profil jam kerja operasional (RSUD, Satpol PP, BPBD, Dishub) memiliki flag `abaikan_libur = True`.
- **Relokasi Validasi `/predict`:** Pengecekan akhir pekan dan hari libur nasional **wajib dipindahkan ke bawah** (setelah wajah pegawai teridentifikasi). Jika profil pegawai memiliki `abaikan_libur = True`, sistem mengizinkan presensi berjalan normal di tanggal merah.

---

## 3. Rancangan Skema Database PostgreSQL

```
┌────────────────────────┐         ┌────────────────────────┐
│    master_jam_kerja    │         │         users          │
├────────────────────────┤         ├────────────────────────┤
│ id (PK)                │         │ user_id (PK)           │
│ nama_shift             │         │ nip                    │
│ jam_masuk              │◄──┐     │ opd_id (FK)            │
│ jam_pulang             │   │     │ jam_kerja_id (FK) ─────┼─── (Fase 1: Default Shift)
│ mulai_scan_masuk       │   │     └───────────┬────────────┘
│ akhir_scan_masuk       │   │                 │
│ mulai_scan_pulang      │   │                 │ 1
│ akhir_scan_pulang      │   │                 │
│ menit_toleransi        │   │                 │ N
│ is_lintas_hari         │   │     ┌───────────▼────────────┐
│ abaikan_libur          │   │     │  roster_jadwal_shift   │
│ opd_id (FK, nullable)  │   │     ├────────────────────────┤
└────────────────────────┘   │     │ id (PK)                │
                             └─────┼─ jam_kerja_id (FK)     │ (Fase 2: Dynamic Roster)
                                   │ user_id (FK)           │
                                   │ tanggal (DATE)         │
                                   │ keterangan             │
                                   └────────────────────────┘
```

### A. Tabel `master_jam_kerja`
```sql
CREATE TABLE IF NOT EXISTS master_jam_kerja (
    id SERIAL PRIMARY KEY,
    nama_shift VARCHAR(100) NOT NULL,
    jam_masuk TIME NOT NULL,
    jam_pulang TIME NOT NULL,
    mulai_scan_masuk TIME NOT NULL,
    akhir_scan_masuk TIME NOT NULL,
    mulai_scan_pulang TIME NOT NULL,
    akhir_scan_pulang TIME NOT NULL,
    menit_toleransi INTEGER DEFAULT 0,
    is_lintas_hari BOOLEAN DEFAULT FALSE,
    abaikan_libur BOOLEAN DEFAULT FALSE,
    opd_id INTEGER REFERENCES master_opd(id) ON DELETE SET NULL, -- NULL = Global
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### B. Fase 1: Penugasan Jam Kerja Statis / Default
Untuk pegawai reguler non-shift, penugasan langsung dikaitkan pada tabel `users`.
```sql
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS jam_kerja_id INTEGER REFERENCES master_jam_kerja(id) ON DELETE SET NULL;
```

### C. Fase 2: Sistem Roster Bergulir (Dynamic Rolling Roster)
Untuk pegawai dengan sistem piket/shift berganti per tanggal (RSUD, Satpol PP, Dishub):
```sql
CREATE TABLE IF NOT EXISTS roster_jadwal_shift (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    tanggal DATE NOT NULL,
    jam_kerja_id INTEGER NOT NULL REFERENCES master_jam_kerja(id) ON DELETE RESTRICT,
    keterangan VARCHAR(100), -- Contoh: 'Piket Pagi', 'Tukar Jaga dengan Budi', 'Lepas Piket'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, tanggal) -- Satu pegawai hanya punya 1 profil shift aktif per tanggal
);

CREATE INDEX IF NOT EXISTS idx_roster_user_tanggal ON roster_jadwal_shift(user_id, tanggal);
```

### D. Fallback Rule (Pencegahan Jadwal Kosong):
Jika pada tanggal tertentu seorang pegawai belum di-plot pada tabel `roster_jadwal_shift` (misal Admin OPD terlambat menyusun jadwal awal bulan), backend otomatis menggunakan `jam_kerja_id` default yang terdaftar di profil `users`.

---

## 4. Rincian Endpoint API yang Akan Dikembangkan

### A. Master Jam Kerja (Super Admin Only)
- `GET /api/jam-kerja`: Mengambil seluruh daftar jam kerja (dengan filter opsional `?opd_id=`).
- `POST /api/jam-kerja`: Membuat jenis jam kerja baru.
- `PUT /api/jam-kerja/:id`: Memperbarui parameter jam kerja.
- `DELETE /api/jam-kerja/:id`: Menghapus profil jam kerja (dengan proteksi jika masih digunakan).

### B. Penugasan Default Pegawai (Admin OPD)
- `PUT /api/users/:user_id/jam-kerja`: Menetapkan jam kerja standar/default seorang pegawai.
- `POST /api/users/bulk-jam-kerja`: Menetapkan jam kerja secara massal berdasarkan daftar NIP.

### C. Modul Roster Bergulir (Admin OPD)
- `GET /api/roster?opd_id=X&bulan=Y&tahun=Z`: Mengambil matriks jadwal shift pegawai selama satu bulan.
- `POST /api/roster/batch`: Menyimpan plotting roster bulanan untuk banyak pegawai sekaligus.
- `PUT /api/roster/swap`: Menangani pertukaran jadwal antar pegawai (*Tukar Jaga*).

### D. Penyesuaian Endpoint Presensi & Laporan
- **`/predict` (Kiosk):** Mengambil jadwal aktif pegawai untuk hari scan (prioritas: Roster Tanggal $\rightarrow$ Fallback Default User), lalu memvalidasi jendela waktu scan dan status keterlambatan.
- **`/report` (Dashboard):** 
  - Menampilkan nama shift pegawai pada kolom tabel.
  - Membandingkan jam scan dengan profil shift yang bersangkutan (bukan jam 08:00 global).
  - Menyesuaikan penentuan status `ABSENT` (hanya menandai alpa jika pegawai dijadwalkan masuk di roster pada hari tersebut).
  - Menambahkan filter pencarian berdasarkan jenis jam kerja/shift.