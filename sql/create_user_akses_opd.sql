-- ===========================================================
-- Tabel Akses Lintas Instansi (Cross-OPD Face Registration)
-- Jalankan script ini di MySQL untuk membuat tabel baru.
-- ===========================================================

CREATE TABLE IF NOT EXISTS `user_akses_opd` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_nip` VARCHAR(50) NOT NULL,
    `opd_id` INT NOT NULL,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- Unique constraint: satu NIP hanya boleh punya satu record per OPD
    CONSTRAINT `uq_user_nip_opd_id` UNIQUE (`user_nip`, `opd_id`),

    -- Foreign Keys
    CONSTRAINT `fk_akses_nip` FOREIGN KEY (`user_nip`) REFERENCES `data_pegawai`(`nip`) ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT `fk_akses_opd` FOREIGN KEY (`opd_id`) REFERENCES `master_opd`(`id`) ON UPDATE CASCADE ON DELETE CASCADE,

    -- Index untuk performa lookup
    INDEX `idx_user_nip` (`user_nip`),
    INDEX `idx_opd_id` (`opd_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
