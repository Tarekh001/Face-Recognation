-- ============================================================================
-- MIGRATION V2.0: PEMISAHAN FISIK TABEL USER & PRESENSI (ASN vs NON-ASN)
-- Target Database: db_face_recognation_v3.0 (PostgreSQL)
-- ============================================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS backup_legacy;

-- 1. Buat Tabel Identitas Khusus ASN & Admin (users_asn)
CREATE TABLE IF NOT EXISTS public.users_asn (
    user_id SERIAL PRIMARY KEY,
    nip VARCHAR(50) UNIQUE NOT NULL REFERENCES public.data_pegawai(nip) ON UPDATE CASCADE ON DELETE RESTRICT,
    pin VARCHAR(50) NOT NULL,
    nama_lengkap VARCHAR(100) NOT NULL,
    username VARCHAR(100) UNIQUE,
    opd_id INTEGER REFERENCES public.master_opd(id) ON DELETE SET NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'asn' CHECK (role IN ('asn', 'admin_opd', 'super_admin')),
    password_hash VARCHAR(255),
    is_face_registered BOOLEAN NOT NULL DEFAULT FALSE,
    approval_status VARCHAR(20) NOT NULL DEFAULT 'approved',
    jam_kerja_id INTEGER REFERENCES public.master_jam_kerja(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_users_asn_opd_id ON public.users_asn(opd_id);
CREATE INDEX IF NOT EXISTS idx_users_asn_role ON public.users_asn(role);
CREATE INDEX IF NOT EXISTS idx_users_asn_pin ON public.users_asn(pin);

-- 2. Buat Tabel Identitas Khusus Tenaga Non-ASN (users_non_asn)
CREATE TABLE IF NOT EXISTS public.users_non_asn (
    non_asn_id SERIAL PRIMARY KEY,
    nik VARCHAR(16) UNIQUE NOT NULL,
    nama_lengkap VARCHAR(100) NOT NULL,
    opd_id INTEGER NOT NULL REFERENCES public.master_opd(id) ON DELETE RESTRICT,
    jam_kerja_id INTEGER REFERENCES public.master_jam_kerja(id) ON DELETE SET NULL,
    is_face_registered BOOLEAN NOT NULL DEFAULT FALSE,
    approval_status VARCHAR(20) NOT NULL DEFAULT 'approved',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_users_non_asn_opd_id ON public.users_non_asn(opd_id);

-- 3. Buat Tabel Presensi Reguler ASN (presensi_asn) - Bersih & Siap Kirim ke SPOT
CREATE TABLE IF NOT EXISTS public.presensi_asn (
    log_id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES public.users_asn(user_id) ON DELETE CASCADE,
    nip VARCHAR(50) NOT NULL REFERENCES public.data_pegawai(nip) ON UPDATE CASCADE,
    user_pin VARCHAR(50) NOT NULL,
    nama_lengkap VARCHAR(100) NOT NULL,
    opd_id INTEGER REFERENCES public.master_opd(id) ON DELETE SET NULL,
    jam_kerja_id INTEGER REFERENCES public.master_jam_kerja(id) ON DELETE SET NULL,
    tanggal_tugas DATE NOT NULL,
    waktu_scan TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    tipe_absen VARCHAR(3) NOT NULL CHECK (tipe_absen IN ('IN', 'OUT')),
    status_kehadiran VARCHAR(20) NOT NULL DEFAULT 'ON_TIME',
    keterlambatan_menit INTEGER NOT NULL DEFAULT 0,
    device_sn VARCHAR(50) NOT NULL DEFAULT 'WEB_APP',
    foto_presensi TEXT,
    spot_sync_status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (spot_sync_status IN ('pending', 'synced', 'failed')),
    spot_synced_at TIMESTAMP,
    spot_response TEXT
);
CREATE INDEX IF NOT EXISTS idx_presensi_asn_tanggal_opd ON public.presensi_asn(tanggal_tugas, opd_id);
CREATE INDEX IF NOT EXISTS idx_presensi_asn_nip_tanggal ON public.presensi_asn(nip, tanggal_tugas);
CREATE INDEX IF NOT EXISTS idx_presensi_asn_user_pin ON public.presensi_asn(user_pin, tanggal_tugas);
CREATE INDEX IF NOT EXISTS idx_presensi_asn_spot_sync ON public.presensi_asn(spot_sync_status);

-- 4. Buat Tabel Presensi Reguler Non-ASN (presensi_non_asn) - Bersih untuk Laporan OPD
CREATE TABLE IF NOT EXISTS public.presensi_non_asn (
    log_id BIGSERIAL PRIMARY KEY,
    non_asn_id INTEGER NOT NULL REFERENCES public.users_non_asn(non_asn_id) ON DELETE CASCADE,
    nik VARCHAR(16) NOT NULL REFERENCES public.users_non_asn(nik) ON UPDATE CASCADE ON DELETE CASCADE,
    nama_lengkap VARCHAR(100) NOT NULL,
    opd_id INTEGER NOT NULL REFERENCES public.master_opd(id) ON DELETE CASCADE,
    jam_kerja_id INTEGER REFERENCES public.master_jam_kerja(id) ON DELETE SET NULL,
    tanggal_tugas DATE NOT NULL,
    waktu_scan TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    tipe_absen VARCHAR(3) NOT NULL CHECK (tipe_absen IN ('IN', 'OUT')),
    status_kehadiran VARCHAR(20) NOT NULL DEFAULT 'ON_TIME',
    keterlambatan_menit INTEGER NOT NULL DEFAULT 0,
    device_sn VARCHAR(50) NOT NULL DEFAULT 'WEB_APP',
    foto_presensi TEXT
);
CREATE INDEX IF NOT EXISTS idx_presensi_non_asn_tanggal_opd ON public.presensi_non_asn(tanggal_tugas, opd_id);
CREATE INDEX IF NOT EXISTS idx_presensi_non_asn_nik_tanggal ON public.presensi_non_asn(nik, tanggal_tugas);

-- 5. Migrasikan Data dari public.users & public.presensi (Jika masih ada di schema public)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'users'
    ) THEN
        -- Pastikan setiap ASN/Admin di users memiliki pasangan di data_pegawai
        INSERT INTO public.data_pegawai (pin, nip, nama_lengkap)
        SELECT
            COALESCE(NULLIF(u.user_pin, ''), 'PIN-' || SUBSTRING(u.user_nip FROM 1 FOR 12)),
            u.user_nip,
            COALESCE(u.nama_lengkap, u.user_nip)
        FROM public.users u
        LEFT JOIN public.data_pegawai dp ON u.user_nip = dp.nip
        WHERE u.role IN ('asn', 'admin_opd', 'super_admin')
          AND u.user_nip IS NOT NULL
          AND dp.nip IS NULL
        ON CONFLICT (nip) DO NOTHING;

        -- Migrasikan ASN, Admin OPD, Super Admin ke users_asn
        INSERT INTO public.users_asn (
            user_id, nip, pin, nama_lengkap, username, opd_id, role,
            password_hash, is_face_registered, approval_status, jam_kerja_id, created_at
        )
        SELECT
            u.user_id,
            u.user_nip,
            COALESCE(NULLIF(dp.pin, ''), NULLIF(u.user_pin, ''), u.user_nip),
            COALESCE(u.nama_lengkap, dp.nama_lengkap, u.user_nip),
            u.username,
            u.opd_id,
            u.role,
            u.password_hash,
            COALESCE(u.is_face_registered, FALSE),
            COALESCE(u.approval_status, 'approved'),
            u.jam_kerja_id,
            COALESCE(u.created_at, CURRENT_TIMESTAMP)
        FROM public.users u
        JOIN public.data_pegawai dp ON u.user_nip = dp.nip
        WHERE u.role IN ('asn', 'admin_opd', 'super_admin')
        ON CONFLICT (nip) DO NOTHING;

        -- Migrasikan Non-ASN ke users_non_asn (pertahankan ID asli pada non_asn_id agar mudah dilacak)
        INSERT INTO public.users_non_asn (
            non_asn_id, nik, nama_lengkap, opd_id, jam_kerja_id,
            is_face_registered, approval_status, created_at
        )
        SELECT
            u.user_id,
            u.user_nip,
            COALESCE(u.nama_lengkap, u.user_nip),
            COALESCE(u.opd_id, 1),
            u.jam_kerja_id,
            COALESCE(u.is_face_registered, FALSE),
            COALESCE(u.approval_status, 'approved'),
            COALESCE(u.created_at, CURRENT_TIMESTAMP)
        FROM public.users u
        WHERE u.role = 'non_asn'
        ON CONFLICT (nik) DO NOTHING;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'presensi'
    ) THEN
        -- Migrasikan log presensi ASN ke presensi_asn (dengan pemetaan user_pin ke PIN SPOT asli)
        INSERT INTO public.presensi_asn (
            log_id, user_id, nip, user_pin, nama_lengkap, opd_id, jam_kerja_id,
            tanggal_tugas, waktu_scan, tipe_absen, status_kehadiran,
            keterlambatan_menit, device_sn, foto_presensi, spot_sync_status
        )
        SELECT
            p.log_id,
            ua.user_id,
            ua.nip,
            ua.pin,
            ua.nama_lengkap,
            ua.opd_id,
            COALESCE(p.jam_kerja_id, ua.jam_kerja_id),
            COALESCE(p.tanggal_tugas, DATE(p.waktu_presensi)),
            p.waktu_presensi,
            COALESCE(p.tipe_absen, 'IN'),
            COALESCE(p.status_kehadiran, 'ON_TIME'),
            COALESCE(p.keterlambatan_menit, 0),
            COALESCE(p.device_sn, 'WEB_APP'),
            p.foto_presensi,
            'pending'
        FROM public.presensi p
        JOIN public.users_asn ua
          ON (p.user_pin = ua.nip OR p.user_pin = ua.pin)
        ON CONFLICT (log_id) DO NOTHING;

        -- Migrasikan log presensi Non-ASN ke presensi_non_asn
        INSERT INTO public.presensi_non_asn (
            log_id, non_asn_id, nik, nama_lengkap, opd_id, jam_kerja_id,
            tanggal_tugas, waktu_scan, tipe_absen, status_kehadiran,
            keterlambatan_menit, device_sn, foto_presensi
        )
        SELECT
            p.log_id,
            una.non_asn_id,
            una.nik,
            una.nama_lengkap,
            una.opd_id,
            COALESCE(p.jam_kerja_id, una.jam_kerja_id),
            COALESCE(p.tanggal_tugas, DATE(p.waktu_presensi)),
            p.waktu_presensi,
            COALESCE(p.tipe_absen, 'IN'),
            COALESCE(p.status_kehadiran, 'ON_TIME'),
            COALESCE(p.keterlambatan_menit, 0),
            COALESCE(p.device_sn, 'WEB_APP'),
            p.foto_presensi
        FROM public.presensi p
        JOIN public.users_non_asn una
          ON p.user_pin = una.nik
        ON CONFLICT (log_id) DO NOTHING;
    END IF;
END $$;

-- Sinkronkan sequence auto-increment
SELECT setval('public.users_asn_user_id_seq', COALESCE((SELECT MAX(user_id) FROM public.users_asn), 1));
SELECT setval('public.users_non_asn_non_asn_id_seq', COALESCE((SELECT MAX(non_asn_id) FROM public.users_non_asn), 1));
SELECT setval('public.presensi_asn_log_id_seq', COALESCE((SELECT MAX(log_id) FROM public.presensi_asn), 1));
SELECT setval('public.presensi_non_asn_log_id_seq', COALESCE((SELECT MAX(log_id) FROM public.presensi_non_asn), 1));

-- 6. Perbarui Tabel roster_jadwal_shift agar mendukung ASN (user_id) & Non-ASN (non_asn_id)
ALTER TABLE public.roster_jadwal_shift
    ADD COLUMN IF NOT EXISTS non_asn_id INTEGER;

ALTER TABLE public.roster_jadwal_shift
    ALTER COLUMN user_id DROP NOT NULL;

ALTER TABLE public.roster_jadwal_shift
    DROP CONSTRAINT IF EXISTS roster_jadwal_shift_user_id_fkey;

-- Pindahkan user_id milik Non-ASN pada roster_jadwal_shift ke kolom non_asn_id
UPDATE public.roster_jadwal_shift r
SET non_asn_id = r.user_id,
    user_id = NULL
WHERE r.user_id IS NOT NULL
  AND EXISTS (SELECT 1 FROM public.users_non_asn una WHERE una.non_asn_id = r.user_id)
  AND NOT EXISTS (SELECT 1 FROM public.users_asn ua WHERE ua.user_id = r.user_id);

ALTER TABLE public.roster_jadwal_shift
    ADD CONSTRAINT roster_jadwal_shift_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES public.users_asn(user_id) ON DELETE CASCADE;

ALTER TABLE public.roster_jadwal_shift
    DROP CONSTRAINT IF EXISTS roster_jadwal_shift_non_asn_id_fkey;

ALTER TABLE public.roster_jadwal_shift
    ADD CONSTRAINT roster_jadwal_shift_non_asn_id_fkey
    FOREIGN KEY (non_asn_id) REFERENCES public.users_non_asn(non_asn_id) ON DELETE CASCADE;

CREATE UNIQUE INDEX IF NOT EXISTS uq_roster_non_asn_tanggal
    ON public.roster_jadwal_shift(non_asn_id, tanggal)
    WHERE non_asn_id IS NOT NULL;

-- 7. Arahkan Foreign Key Tabel Pendukung ke users_asn
ALTER TABLE public.jadwal_kegiatan
    DROP CONSTRAINT IF EXISTS jadwal_kegiatan_created_by_fkey;
ALTER TABLE public.jadwal_kegiatan
    ADD CONSTRAINT jadwal_kegiatan_created_by_fkey
    FOREIGN KEY (created_by) REFERENCES public.users_asn(user_id) ON DELETE RESTRICT;

ALTER TABLE public.user_akses_opd
    DROP CONSTRAINT IF EXISTS user_akses_opd_user_nip_fkey;
ALTER TABLE public.user_akses_opd
    ADD CONSTRAINT user_akses_opd_user_nip_fkey
    FOREIGN KEY (user_nip) REFERENCES public.users_asn(nip) ON UPDATE CASCADE ON DELETE CASCADE;

ALTER TABLE public.user_admin
    DROP CONSTRAINT IF EXISTS user_admin_user_id_fkey;
ALTER TABLE public.user_admin
    ADD CONSTRAINT user_admin_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES public.users_asn(user_id) ON DELETE CASCADE;

ALTER TABLE public.devices
    DROP CONSTRAINT IF EXISTS devices_registered_by_fkey;
ALTER TABLE public.devices
    ADD CONSTRAINT devices_registered_by_fkey
    FOREIGN KEY (registered_by) REFERENCES public.users_asn(user_id) ON DELETE SET NULL;

ALTER TABLE public.audit_logs
    DROP CONSTRAINT IF EXISTS audit_logs_actor_user_id_fkey;
ALTER TABLE public.audit_logs
    ADD CONSTRAINT audit_logs_actor_user_id_fkey
    FOREIGN KEY (actor_user_id) REFERENCES public.users_asn(user_id) ON DELETE SET NULL;

-- 8. Pindahkan Tabel Lama (users & presensi) ke Schema backup_legacy agar public di DBeaver Bersih
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'presensi'
    ) THEN
        ALTER TABLE public.presensi SET SCHEMA backup_legacy;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'users'
    ) THEN
        ALTER TABLE public.users SET SCHEMA backup_legacy;
    END IF;
END $$;

COMMIT;
