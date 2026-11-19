-- Migrasi Prioritas 4: Kolom foto bukti presensi harian (path relatif file WebP)
ALTER TABLE presensi
ADD COLUMN IF NOT EXISTS foto_presensi TEXT;
