-- ==============================================
-- MIGRATION: Make opd_id NULLABLE on jadwal_kegiatan
-- Purpose: Support "Global Events" (Cross-OPD)
--          created by Super Admin where opd_id = NULL.
--          NULL opd_id = Global Event (visible to all OPDs).
--          Non-NULL opd_id = Local Event (internal to one OPD).
-- Date: 2026-06-14
-- ==============================================

ALTER TABLE jadwal_kegiatan
ALTER COLUMN opd_id DROP NOT NULL;

-- Verify
SELECT column_name, is_nullable, data_type
FROM information_schema.columns
WHERE table_name = 'jadwal_kegiatan' AND column_name = 'opd_id';
