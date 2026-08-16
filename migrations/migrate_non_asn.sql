-- ============================================================
-- Migration: Support Non-ASN Registration (NIK 16-digit)
-- Stores NIK in existing 'user_nip' column with role='non_asn'
-- ============================================================

-- Step 1: Make user_nip nullable (Non-ASN won't have data_pegawai entry)
ALTER TABLE users ALTER COLUMN user_nip DROP NOT NULL;

-- Step 2: Drop strict FK and re-add as nullable-safe
-- (allows NULL for Non-ASN, keeps referential integrity for ASN)
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_user_nip_fkey;
ALTER TABLE users ADD CONSTRAINT users_user_nip_fkey
  FOREIGN KEY (user_nip) REFERENCES data_pegawai(nip) ON DELETE SET NULL
  NOT VALID;

-- Step 3: Also relax user_akses_opd FK for Non-ASN
ALTER TABLE user_akses_opd DROP CONSTRAINT IF EXISTS user_akses_opd_user_nip_fkey;
ALTER TABLE user_akses_opd ADD CONSTRAINT user_akses_opd_user_nip_fkey
  FOREIGN KEY (user_nip) REFERENCES users(user_nip) ON DELETE CASCADE
  NOT VALID;

-- Step 4: Also relax presensi_kegiatan FK for Non-ASN
ALTER TABLE presensi_kegiatan DROP CONSTRAINT IF EXISTS presensi_kegiatan_nip_fkey;

-- Step 5: Add index for role-based queries
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

-- NOTE: Existing ASN data is unaffected. Only new Non-ASN registrations
-- will have role='non_asn' and their NIK stored in user_nip column.
