# Panduan Lengkap Deployment ke Windows Server (via GitHub)

Dokumen ini berisi panduan langkah demi langkah secara berurutan untuk men-deploy pembaruan **Smart Presensi (Plan Kerja 2.0 & 2.1: Pemisahan Tabel ASN vs Non-ASN, Sinkronisasi 18.314 Pegawai CSV SPOT, Perbaikan PIN, & Cron Job SPOT)** dari komputer lokal ke **Windows Server** menggunakan **GitHub**.

---

## Arsitektur Repositori GitHub Anda

Sistem terdiri dari **2 repositori GitHub** yang saling terhubung:
1. **Backend (Flask + FaceNet + MTCNN + Cron Job SPOT):**
   - Path Lokal: `d:\Project Diskominfo\project2\Face_Recognition_AI_Secure`
   - Remote GitHub: `https://github.com/Tarekh001/Face-Recognation.git`
2. **Frontend Web Admin (React + Vite + Tailwind):**
   - Path Lokal: `C:\Users\ASUS\Web_Face_Recognation`
   - Remote GitHub: `https://github.com/Tarekh001/Web_Face_Recognation_Secure.git`

---

## TAHAP 1: Push Kode Terbaru dari Komputer Lokal ke GitHub

Sebelum masuk ke Windows Server, pastikan seluruh perubahan kode di komputer lokal Anda sudah di-*commit* dan di-*push* ke GitHub.

### 1.1. Push Repositori Backend (`Face-Recognation`)
Buka **PowerShell** di komputer lokal Anda, lalu jalankan:

```powershell
cd "d:\Project Diskominfo\project2\Face_Recognition_AI_Secure"

# Periksa file yang berubah dan file baru (termasuk folder migrations/ dan api/spot_*.py)
git status

# Tambahkan seluruh file kode dan skrip migrasi
git add app.py models.py .gitignore plan_kerja2.0.md plan_kerja2.1.md panduan_deploy_windows_server.md
git add api/
git add migrations/migrate_v2_split_asn_non_asn.sql
git add migrations/run_migration_v2.py
git add migrations/sync_pegawai_and_fix_pins.py

# Commit dengan pesan yang jelas
git commit -m "feat(v2.1): split ASN/Non-ASN tables, add SPOT cron sync & CSV PIN repair"

# Push ke GitHub (sesuaikan nama branch utama Anda, misal main atau master)
git push origin HEAD
```

### 1.2. Push Repositori Frontend (`Web_Face_Recognation_Secure`)
Masih di **PowerShell** komputer lokal Anda, jalankan:

```powershell
cd "C:\Users\ASUS\Web_Face_Recognation"

# Periksa status perubahan frontend
git status

# Tambahkan seluruh perubahan komponen dan halaman baru (SpotSyncPage.jsx)
git add .

# Commit perubahan
git commit -m "feat(v2.1): add SpotSyncPage, CSV pegawai uploader, and SPOT status badges"

# Push ke GitHub
git push origin HEAD
```

> **Catatan Penting File Non-Git (`.gitignore`):**
> 1. File CSV terbaru (`e:\Documents\pegawai_260930193431_261116164935.csv`) dapat disalin ke Windows Server melalui *Remote Desktop (RDP) Copy-Paste* untuk dijalankan dengan `sync_pegawai_and_fix_pins.py`, atau diunggah langsung lewat menu Web **Sinkronisasi SPOT -> Konfigurasi & Payload -> Unggah CSV Data Pegawai**.
> 2. Folder biometrik `samples/` dan `samples_embedding/` diabaikan oleh Git demi keamanan privasi biometrik. Skrip `sync_pegawai_and_fix_pins.py` di server akan otomatis me-rename folder `samples/` dan `samples_embedding/` yang sudah ada di server.

---

## TAHAP 2: Backup Database & Folder Biometrik di Windows Server (Wajib)

Masuk ke **Windows Server** Anda (melalui *Remote Desktop / RDP*), buka **PowerShell sebagai Administrator**, lalu lakukan backup sebelum mengubah database.

### 2.1. Backup Database PostgreSQL (`pg_dump`)
Sesuaikan path instalasi PostgreSQL dan port di Windows Server Anda (umumnya port `5432` atau `5434`):

```powershell
New-Item -ItemType Directory -Force -Path "C:\Backup_Presensi"

& "C:\Program Files\PostgreSQL\16\bin\pg_dump.exe" -h localhost -p 5432 -U postgres -F c -b -v -f "C:\Backup_Presensi\db_face_before_v21_$(Get-Date -Format 'yyyyMMdd_HHmm').backup" db_face_recognation_v3.0
```

### 2.2. Backup Folder `samples` dan `samples_embedding` di Server
```powershell
$ServerBackendDir = "C:\Project\Face-Recognation"

Copy-Item -Path "$ServerBackendDir\samples" -Destination "C:\Backup_Presensi\samples_backup" -Recurse -Force
Copy-Item -Path "$ServerBackendDir\samples_embedding" -Destination "C:\Backup_Presensi\samples_embedding_backup" -Recurse -Force
```

---

## TAHAP 3: Pull & Konfigurasi Backend di Windows Server

### 3.1. Pull Kode Backend dari GitHub
```powershell
cd "C:\Project\Face-Recognation"
git pull origin main
```

### 3.2. Aktifkan Virtual Environment & Install Dependensi Produksi
```powershell
cd "C:\Project\Face-Recognation"
.\Faceenv\Scripts\Activate.ps1

pip install -r requirements.txt
pip install waitress requests
```

### 3.3. Buat atau Perbarui File `.env` di Windows Server
Buat/edit file `C:\Project\Face-Recognation\.env`:

```ini
DB_HOST=localhost
DB_PORT=5432
DB_NAME=db_face_recognation_v3.0
DB_USER=postgres
DB_PASSWORD=ISI_PASSWORD_POSTGRES_SERVER_ANDA
SECRET_KEY=ISI_DENGAN_KUNCI_ACAK_PANJANG_PRODUKSI
SPOT_BASE_URL=https://absen.meteoronyx.my.id
PORT=5000
FLASK_DEBUG=0
```

---

## TAHAP 4: Jalankan Migrasi Database & Perbaikan PIN di Windows Server

Tetap di dalam **PowerShell Windows Server** dengan `Faceenv` yang aktif (`C:\Project\Face-Recognation`):

### 4.1. Jalankan Migrasi Pemisahan Tabel ASN vs Non-ASN (`run_migration_v2.py`)
```powershell
# 1. Cek terlebih dahulu dengan mode Dry-Run (Simulasi aman)
python migrations/run_migration_v2.py --dry-run

# 2. Eksekusi migrasi pemisahan tabel
python migrations/run_migration_v2.py --execute
```

### 4.2. Jalankan Sinkronisasi CSV 18.314 Pegawai SPOT & Perbaikan PIN (`sync_pegawai_and_fix_pins.py`)
Salin file `pegawai_260930193431_261116164935.csv` ke Windows Server (misalnya di `C:\Backup_Presensi\pegawai_260930193431_261116164935.csv`), lalu jalankan:

```powershell
# 1. Uji simulasi terlebih dahulu (--dry-run)
python migrations/sync_pegawai_and_fix_pins.py --csv "C:\Backup_Presensi\pegawai_260930193431_261116164935.csv" --dry-run

# 2. Eksekusi permanen (--execute)
python migrations/sync_pegawai_and_fix_pins.py --csv "C:\Backup_Presensi\pegawai_260930193431_261116164935.csv" --execute
```

---

## TAHAP 5: Pull & Build Frontend React di Windows Server

```powershell
cd "C:\Project\Web_Face_Recognation_Secure"
git pull origin main

# Pastikan .env.production berisi:
# VITE_API_BASE=http://IP_ATAU_DOMAIN_SERVER_ANDA:5000/api

npm install
npm run build
```

---

## TAHAP 6: Menjalankan Layanan Permanen di Windows Server

### 6.1. Menjalankan Backend Flask dengan Waitress + NSSM
Buat file `C:\Project\Face-Recognation\start_server.bat`:

```bat
@echo off
cd /d "C:\Project\Face-Recognation"
call "C:\Project\Face-Recognation\Faceenv\Scripts\activate.bat"
waitress-serve --host=0.0.0.0 --port=5000 --threads=8 app:app
```

Daftarkan ke Windows Service menggunakan NSSM:

```powershell
nssm install SmartPresensiBackend "C:\Project\Face-Recognation\start_server.bat"
nssm set SmartPresensiBackend AppDirectory "C:\Project\Face-Recognation"
nssm set SmartPresensiBackend AppStdout "C:\Project\Face-Recognation\server_out.log"
nssm set SmartPresensiBackend AppStderr "C:\Project\Face-Recognation\server_err.log"
nssm start SmartPresensiBackend
```

### 6.2. Menayangkan Frontend (`dist/`)
- **Menggunakan `serve`:** `serve -s "C:\Project\Web_Face_Recognation_Secure\dist" -l 3000`
- **Menggunakan IIS / Nginx:** Arahkan root ke folder `dist/` dengan fallback SPA ke `/index.html`.

### 6.3. Buka Port di Windows Defender Firewall
```powershell
New-NetFirewallRule -DisplayName "Smart Presensi API (5000)" -Direction Inbound -LocalPort 5000 -Protocol TCP -Action Allow
New-NetFirewallRule -DisplayName "Smart Presensi Web (3000)" -Direction Inbound -LocalPort 3000 -Protocol TCP -Action Allow
```

---

## TAHAP 7: Checklist Verifikasi Pasca-Deploy (Go-Live)

- [ ] Indikator koneksi di kanan atas header Web Admin berstatus **"Server Terhubung"**.
- [ ] Menu **Data ASN** menampilkan `NINA SETYAWATI` (`200203182025212001`), `SYLVIA IRAWAN WINATA PUTRI` (`199608302025212058`), dan `Diaz Mardiwibowo` (`196704132001121002`).
- [ ] Menu **Data Non-ASN** menampilkan `Eko Setyawan`, `Triwulan Ambarwati`, dan `Muhamad Tarekh`.
- [ ] Login Admin OPD menggunakan `admin01.diskominfo@kabtangerang.go.id` berjalan lancar dan menampilkan badge status SPOT pada **Rekapitulasi -> Harian ASN**.
- [ ] Menu Super Admin **Konfigurasi -> Sinkronisasi SPOT** berhasil menjalankan **Handshake Perangkat ke SPOT**, **Kirim Antrean Sekarang**, dan memperbarui waktu **Eksekusi Cron Terakhir** setiap 5 menit.
