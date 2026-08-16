-- ===========================================================
-- PATCH: Tambah kolom approval_status ke tabel user_akses_opd
-- Kolom ini dibutuhkan oleh model UserAksesOpd untuk fitur approval
-- ===========================================================

ALTER TABLE `user_akses_opd`
ADD COLUMN `approval_status` VARCHAR(20) NOT NULL DEFAULT 'approved'
AFTER `opd_id`;

-- Update semua record lama yang belum punya value
UPDATE `user_akses_opd` SET `approval_status` = 'approved' WHERE `approval_status` IS NULL;
