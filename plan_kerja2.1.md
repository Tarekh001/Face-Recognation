# Plan Kerja 2.1: Menu Sinkronisasi SPOT & Penjadwalan Otomatis (Cron Job)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task, together with `antislop`, `antislop-ui`, `antislop-code`, `antislop-copywriting`, and `antislop-layoutmobile`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Membangun fitur pengiriman otomatis terpadu (Background Cron Job setiap 5 menit) dan halaman kendali **Sinkronisasi SPOT** khusus Super Admin, disertai visibilitas status pengiriman log ASN per instansi untuk Admin OPD pada halaman Rekapitulasi Harian ASN.

**Architecture:** Menggunakan arsitektur **Dual-Trigger Outbox Pattern** pada tabel `presensi_asn`. Setiap log presensi ASN disimpan dengan `spot_sync_status = 'pending'`. *Background Scheduler (Cron Worker)* berjalan otomatis setiap 5 menit untuk mengirimkan antrean `'pending'` dan `'failed'` ke server SPOT tujuan (`SPOT_BASE_URL`). Ke-4 kolom pelengkap setelah `{UserPIN}` dan `{Time}` (`{Status}`, `{VerifyMode}`, `{Validation}`, `{WorkCode}`) memiliki nilai standar ZKTeco ADMS (`0/1`, `15`, `0`, `0`) yang dapat dikustomisasi langsung dari UI Konfigurasi SPOT.

**Tech Stack:** Python 3.11+, Flask, Background Cron Worker (`api/spot_scheduler.py`), PostgreSQL (`presensi_asn` & `app_settings`), React + Tailwind CSS (*Modern Executive Civic* `ENERGY 2 / RHYTHM 2 / MOTION 2`).

**Spec:** `plan_kerja2.1.md`
