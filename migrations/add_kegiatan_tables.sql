-- ==============================================
-- MIGRATION: Add Jadwal Kegiatan Tables
-- Purpose: Create tables for "Jadwal Kegiatan"
--          (Out-of-Office Activity Schedule) with
--          geofencing support and extend presensi
--          table with GPS coordinates.
-- Date: 2026-06-14
-- ==============================================

-- ── 1. Tabel Jadwal Kegiatan ──
CREATE TABLE IF NOT EXISTS jadwal_kegiatan (
    id              SERIAL PRIMARY KEY,
    nama_kegiatan   VARCHAR(150) NOT NULL,
    keterangan      TEXT,
    alamat_lokasi   TEXT,
    latitude_target  DOUBLE PRECISION NOT NULL,
    longitude_target DOUBLE PRECISION NOT NULL,
    radius_toleransi INTEGER NOT NULL DEFAULT 100,
    tanggal_mulai   DATE NOT NULL,
    tanggal_selesai DATE NOT NULL,
    opd_id          INTEGER NOT NULL REFERENCES master_opd(id) ON DELETE RESTRICT,
    created_by      INTEGER NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
    created_at      TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'Asia/Jakarta')
);

-- ── 2. Tabel Peserta Kegiatan (Many-to-Many Bridge) ──
CREATE TABLE IF NOT EXISTS peserta_kegiatan (
    id              SERIAL PRIMARY KEY,
    kegiatan_id     INTEGER NOT NULL REFERENCES jadwal_kegiatan(id) ON DELETE CASCADE,
    nip             VARCHAR(50) NOT NULL REFERENCES data_pegawai(nip) ON DELETE CASCADE,
    CONSTRAINT uq_kegiatan_nip UNIQUE (kegiatan_id, nip)
);

-- ── 3. Extend Presensi Table — Add GPS & Kegiatan columns ──
ALTER TABLE presensi ADD COLUMN IF NOT EXISTS latitude_scan  DOUBLE PRECISION;
ALTER TABLE presensi ADD COLUMN IF NOT EXISTS longitude_scan DOUBLE PRECISION;
ALTER TABLE presensi ADD COLUMN IF NOT EXISTS kegiatan_id    INTEGER REFERENCES jadwal_kegiatan(id) ON DELETE SET NULL;

-- ── 4. Indexes for performance ──
CREATE INDEX IF NOT EXISTS idx_kegiatan_opd ON jadwal_kegiatan(opd_id);
CREATE INDEX IF NOT EXISTS idx_kegiatan_tanggal ON jadwal_kegiatan(tanggal_mulai, tanggal_selesai);
CREATE INDEX IF NOT EXISTS idx_peserta_kegiatan_id ON peserta_kegiatan(kegiatan_id);
CREATE INDEX IF NOT EXISTS idx_peserta_nip ON peserta_kegiatan(nip);
CREATE INDEX IF NOT EXISTS idx_presensi_kegiatan ON presensi(kegiatan_id) WHERE kegiatan_id IS NOT NULL;

-- ── Verify ──
SELECT table_name FROM information_schema.tables
WHERE table_name IN ('jadwal_kegiatan', 'peserta_kegiatan');

SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'presensi'
AND column_name IN ('latitude_scan', 'longitude_scan', 'kegiatan_id');
