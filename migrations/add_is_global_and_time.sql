-- =============================================================

-- Migration: Add is_global, jam_mulai, jam_selesai to jadwal_kegiatan
-- Run AFTER: alter_kegiatan_opd_nullable.sql
-- =============================================================

-- 1. Add explicit is_global boolean column (default FALSE for existing rows)
ALTER TABLE jadwal_kegiatan
    ADD COLUMN IF NOT EXISTS is_global BOOLEAN NOT NULL DEFAULT FALSE;

-- Backfill: mark existing rows where opd_id IS NULL as Global
UPDATE jadwal_kegiatan
SET is_global = TRUE
WHERE opd_id IS NULL;

-- 2. Add time boundary columns (nullable — optional for each event)
ALTER TABLE jadwal_kegiatan
    ADD COLUMN IF NOT EXISTS jam_mulai TIME;

ALTER TABLE jadwal_kegiatan
    ADD COLUMN IF NOT EXISTS jam_selesai TIME;
