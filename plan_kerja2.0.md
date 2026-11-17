# Plan Kerja 2.0: Pemisahan Database ASN & Non-ASN serta Integrasi Push SPOT

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Memisahkan secara fisik tabel identitas pengguna (`users_asn` dan `users_non_asn`) serta tabel presensi reguler (`presensi_asn` dan `presensi_non_asn`) di PostgreSQL lokal dan server, membersihkan kolom yang tidak terpakai, menyelaraskan struktur kolom dengan tampilan Dashboard, lalu pada tahap akhir mengaktifkan pengiriman log presensi ASN ke server SPOT (`https://absen.meteoronyx.my.id/iclock/cdata`).

**Architecture:** Menggunakan pendekatan **Opsi 2 (Physical Dual-Domain Separation)**. Domain ASN (`users_asn` dan `presensi_asn`) dikunci secara ketat (*Foreign Key* `VALID`) ke tabel master `data_pegawai` hasil sinkronisasi SPOT sehingga setiap transaksi ASN dijamin memiliki `user_pin` SPOT dan `nip` 18 digit yang valid. Domain Non-ASN (`users_non_asn` dan `presensi_non_asn`) berdiri mandiri per OPD menggunakan `nik` 16 digit tanpa mencemari antrean pengiriman SPOT.

**Tech Stack:** Python 3.11+, Flask, Flask-SQLAlchemy, PostgreSQL (`db_face_recognation_v3.0`), `psycopg2`, `requests` (untuk HTTP Push iClock/ADMS ke SPOT), React + Vite (Frontend Dashboard), Flutter (Mobile Kiosk).

**Spec:** `plan_kerja2.0.md`

---

## Global Constraints

1. **Penyimpanan Bukti Foto di Disk:** Dilarang menyimpan BLOB/Base64 foto di PostgreSQL; `foto_presensi TEXT` hanya menyimpan path relatif `/static/uploads/presensi/YYYY/MM/DD/{id}_{tipe}_{timestamp}.webp` (~30 KB).
2. **Ambang Batas Biometrik Tetap 0.75 (75.0%):** `THRESHOLD = 0.75` pada pengenalan wajah tidak boleh diturunkan.
3. **Urutan Pengerjaan Bertahap:** Kerjakan **(1) Migrasi Database Lokal & ORM Backend**, **(2) Penyesuaian Endpoint API & Verifikasi UI Lokal**, **(3) Paket Migrasi Database Server**, dan **terakhir (4) Modul Integrasi Push Log Presensi ASN ke API SPOT (`https://absen.meteoronyx.my.id`)**.
4. **Kompatibilitas Kontrak JSON Frontend & Kiosk:** Seluruh respons JSON ke Web Dashboard (`/api/report`, `/api/manage-asn`, `/api/roster`) dan Flutter Kiosk (`/api/predict`, `/api/register/mobile`) wajib mempertahankan nama properti yang diharapkan klien agar tidak ada fitur UI yang rusak.
5. **Zero Data Loss saat Migrasi:** Seluruh data eksisting di DBeaver wajib dimigrasikan secara utuh dan tabel lama disimpan sebagai cadangan `_legacy_users` dan `_legacy_presensi`.
