-- ============================================================
-- Migration: Make user_pin NULLABLE in presensi table
-- Non-ASN users don't have a PIN from data_pegawai.
-- We use NIP as fallback identifier stored in user_pin column.
-- ============================================================

-- Step 1: Make user_pin nullable
ALTER TABLE presensi ALTER COLUMN user_pin DROP NOT NULL;

-- Step 2: Add index on (user_pin, waktu_presensi) for efficient lookups
-- (Already has index on user_pin, but combo index helps duplicate checks)
CREATE INDEX IF NOT EXISTS idx_presensi_pin_waktu ON presensi(user_pin, waktu_presensi);

-- NOTE: For Non-ASN users, we store user.nip (the 16-digit NIK) in user_pin column
-- as a fallback identifier. This keeps all existing queries working without schema redesign.
