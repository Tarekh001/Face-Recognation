-- ==============================================
-- MIGRATION: Dynamic Settings & Custom Holidays
-- PostgreSQL Version
-- ==============================================

-- 1. Tabel Pengaturan Sistem (Key-Value)
CREATE TABLE IF NOT EXISTS app_settings (
    setting_key VARCHAR(50) PRIMARY KEY,
    setting_value VARCHAR(100) NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Default Values
-- PostgreSQL: ON CONFLICT ... DO NOTHING replaces MySQL ON DUPLICATE KEY UPDATE
INSERT INTO app_settings (setting_key, setting_value, description) VALUES
    ('JAM_MASUK_MULAI',  '06:00:00', 'Jam mulai sesi absen masuk'),
    ('JAM_MASUK_AKHIR',  '12:00:00', 'Jam batas akhir absen masuk'),
    ('BATAS_TERLAMBAT',  '08:00:00', 'Batas jam presensi dinyatakan ON_TIME'),
    ('JAM_KELUAR_MULAI', '15:00:00', 'Jam mulai sesi absen pulang'),
    ('JAM_KELUAR_AKHIR', '20:00:00', 'Jam batas akhir absen pulang')
ON CONFLICT (setting_key) DO NOTHING;

-- 2. Tabel Hari Libur Custom (Cuti Bersama, dll)
CREATE TABLE IF NOT EXISTS hari_libur_custom (
    id SERIAL PRIMARY KEY,
    tanggal DATE NOT NULL UNIQUE,
    keterangan VARCHAR(200) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
