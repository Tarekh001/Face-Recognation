-- ==============================================
-- MIGRATION: Sync ALL users to data_pegawai
-- Purpose: Ensure LEFT JOIN in /api/report always
--          resolves real names for admins & interns.
-- ==============================================

-- Sync every user that has a PIN but is missing
-- from data_pegawai (admins, interns, etc.)
-- PostgreSQL: INSERT ... ON CONFLICT replaces MySQL INSERT IGNORE
INSERT INTO data_pegawai (pin, nip, nama_lengkap)
SELECT user_pin, user_nip, nama_lengkap
FROM users
WHERE user_pin IS NOT NULL
  AND user_pin NOT IN (SELECT pin FROM data_pegawai)
ON CONFLICT (pin) DO NOTHING;

-- Verify: show any users still missing from data_pegawai
SELECT u.user_id, u.user_pin, u.user_nip, u.nama_lengkap, u.role,
       dp.id AS pegawai_id
FROM users u
LEFT JOIN data_pegawai dp ON u.user_pin = dp.pin
WHERE dp.id IS NULL AND u.user_pin IS NOT NULL;
