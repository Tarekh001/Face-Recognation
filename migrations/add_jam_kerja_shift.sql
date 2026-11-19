-- ============================================================================
-- MIGRATION: Modul Manajemen Jam Kerja & Sistem Shift (PLAN_JAM_KERJA.md)
-- ============================================================================

-- 1. Tabel Master Jam Kerja
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
    opd_id INTEGER REFERENCES master_opd(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Kolom Default Jam Kerja pada Tabel users (Fase 1)
ALTER TABLE users
ADD COLUMN IF NOT EXISTS jam_kerja_id INTEGER REFERENCES master_jam_kerja(id) ON DELETE SET NULL;

-- 3. Tabel Roster Jadwal Shift Bergulir (Fase 2)
CREATE TABLE IF NOT EXISTS roster_jadwal_shift (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    tanggal DATE NOT NULL,
    jam_kerja_id INTEGER NOT NULL REFERENCES master_jam_kerja(id) ON DELETE RESTRICT,
    keterangan VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, tanggal)
);

CREATE INDEX IF NOT EXISTS idx_roster_user_tanggal ON roster_jadwal_shift(user_id, tanggal);

-- 4. Kolom tanggal_tugas & jam_kerja_id pada Tabel presensi (Dukungan Shift Lintas Hari / Overnight)
ALTER TABLE presensi
ADD COLUMN IF NOT EXISTS tanggal_tugas DATE,
ADD COLUMN IF NOT EXISTS jam_kerja_id INTEGER REFERENCES master_jam_kerja(id) ON DELETE SET NULL;

UPDATE presensi
SET tanggal_tugas = DATE(waktu_presensi)
WHERE tanggal_tugas IS NULL;

CREATE INDEX IF NOT EXISTS idx_presensi_tanggal_tugas ON presensi(tanggal_tugas);
