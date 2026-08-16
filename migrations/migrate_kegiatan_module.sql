-- ============================================
-- Migration: Presensi Kegiatan Module
-- Date: 2026-07-06
-- Description:
--   1. Drop legacy peserta_kegiatan (per-NIP)
--   2. Create undangan_kegiatan (per-OPD invitation)
--   3. Create presensi_kegiatan (attendance log)
--   4. Alter jadwal_kegiatan: make lat/lng nullable
-- ============================================

-- Step 1: Drop legacy table
DROP TABLE IF EXISTS peserta_kegiatan CASCADE;

-- Step 2: Make lat/lng nullable (some events may not need geofencing)
ALTER TABLE jadwal_kegiatan ALTER COLUMN latitude_target DROP NOT NULL;
ALTER TABLE jadwal_kegiatan ALTER COLUMN longitude_target DROP NOT NULL;

-- Step 3: Create undangan per-OPD table
CREATE TABLE IF NOT EXISTS undangan_kegiatan (
    id SERIAL PRIMARY KEY,
    kegiatan_id INTEGER NOT NULL REFERENCES jadwal_kegiatan(id) ON DELETE CASCADE,
    opd_id INTEGER NOT NULL REFERENCES master_opd(id),
    CONSTRAINT uq_kegiatan_opd UNIQUE (kegiatan_id, opd_id)
);

-- Step 4: Create presensi kegiatan table
CREATE TABLE IF NOT EXISTS presensi_kegiatan (
    id BIGSERIAL PRIMARY KEY,
    kegiatan_id INTEGER NOT NULL REFERENCES jadwal_kegiatan(id),
    nip VARCHAR(50) NOT NULL REFERENCES data_pegawai(nip),
    waktu_scan TIMESTAMP NOT NULL DEFAULT NOW(),
    device_sn VARCHAR(50) NOT NULL,
    latitude_scan DOUBLE PRECISION,
    longitude_scan DOUBLE PRECISION,
    CONSTRAINT uq_presensi_kegiatan_nip UNIQUE (kegiatan_id, nip)
);

-- Step 5: Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_undangan_kegiatan_id ON undangan_kegiatan(kegiatan_id);
CREATE INDEX IF NOT EXISTS idx_undangan_opd_id ON undangan_kegiatan(opd_id);
CREATE INDEX IF NOT EXISTS idx_presensi_kegiatan_kegiatan ON presensi_kegiatan(kegiatan_id);
CREATE INDEX IF NOT EXISTS idx_presensi_kegiatan_nip ON presensi_kegiatan(nip);
