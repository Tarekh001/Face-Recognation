-- --------------------------------------------------------
-- Host:                         127.0.0.1
-- Server version:               8.4.3 - MySQL Community Server - GPL
-- Server OS:                    Win64
-- HeidiSQL Version:             12.8.0.6908
-- --------------------------------------------------------

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET NAMES utf8 */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;


-- Dumping database structure for db_face_recognation_v2.0
CREATE DATABASE IF NOT EXISTS `db_face_recognation_v2.0` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci */ /*!80016 DEFAULT ENCRYPTION='N' */;
USE `db_face_recognation_v2.0`;

-- Dumping structure for table db_face_recognation_v2.0.audit_logs
CREATE TABLE IF NOT EXISTS `audit_logs` (
  `log_id` bigint NOT NULL AUTO_INCREMENT,
  `actor_user_id` int DEFAULT NULL,
  `action` varchar(50) COLLATE utf8mb4_general_ci NOT NULL,
  `target_table` varchar(50) COLLATE utf8mb4_general_ci NOT NULL,
  `target_record_id` varchar(50) COLLATE utf8mb4_general_ci NOT NULL,
  `ip_address` varchar(50) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `keterangan_detail` text COLLATE utf8mb4_general_ci,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`log_id`),
  KEY `actor_user_id` (`actor_user_id`),
  CONSTRAINT `audit_logs_ibfk_1` FOREIGN KEY (`actor_user_id`) REFERENCES `users` (`user_id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table db_face_recognation_v2.0.data_pegawai
CREATE TABLE IF NOT EXISTS `data_pegawai` (
  `id` int NOT NULL AUTO_INCREMENT,
  `pin` varchar(50) COLLATE utf8mb4_general_ci NOT NULL,
  `nip` varchar(50) COLLATE utf8mb4_general_ci NOT NULL,
  `nama_lengkap` varchar(100) COLLATE utf8mb4_general_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `pin` (`pin`),
  UNIQUE KEY `nip` (`nip`)
) ENGINE=InnoDB AUTO_INCREMENT=10793 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table db_face_recognation_v2.0.devices
CREATE TABLE IF NOT EXISTS `devices` (
  `sn` varchar(50) COLLATE utf8mb4_general_ci NOT NULL,
  `name` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `device_name` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `mac_address` varchar(50) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `ip_address` varchar(50) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `fw_version` varchar(50) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `platform` varchar(50) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `last_activity` datetime DEFAULT NULL,
  `timezone` varchar(50) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `verified` tinyint(1) DEFAULT '0',
  `initial_sync_completed` tinyint(1) DEFAULT '0',
  `user_count` int DEFAULT '0',
  `transaction_count` int DEFAULT '0',
  PRIMARY KEY (`sn`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table db_face_recognation_v2.0.master_opd
CREATE TABLE IF NOT EXISTS `master_opd` (
  `id` int NOT NULL AUTO_INCREMENT,
  `nama_opd` varchar(100) COLLATE utf8mb4_general_ci NOT NULL,
  `kode_opd` varchar(50) COLLATE utf8mb4_general_ci NOT NULL,
  `alamat_opd` text COLLATE utf8mb4_general_ci,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `kode_opd` (`kode_opd`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table db_face_recognation_v2.0.presensi
CREATE TABLE IF NOT EXISTS `presensi` (
  `log_id` bigint NOT NULL AUTO_INCREMENT,
  `device_sn` varchar(50) COLLATE utf8mb4_general_ci NOT NULL,
  `user_pin` varchar(50) COLLATE utf8mb4_general_ci NOT NULL,
  `waktu_presensi` datetime NOT NULL,
  `tipe_absen` enum('IN','OUT') COLLATE utf8mb4_general_ci NOT NULL,
  `status_kehadiran` enum('ON_TIME','LATE','EARLY_LEAVE') COLLATE utf8mb4_general_ci NOT NULL,
  `keterlambatan_menit` int DEFAULT '0',
  PRIMARY KEY (`log_id`,`waktu_presensi`),
  KEY `idx_user_pin` (`user_pin`),
  KEY `idx_device_sn` (`device_sn`)
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
/*!50100 PARTITION BY RANGE (((year(`waktu_presensi`) * 100) + month(`waktu_presensi`)))
(PARTITION p202603 VALUES LESS THAN (202604) ENGINE = InnoDB,
 PARTITION p202604 VALUES LESS THAN (202605) ENGINE = InnoDB,
 PARTITION p202605 VALUES LESS THAN (202606) ENGINE = InnoDB,
 PARTITION p202606 VALUES LESS THAN (202607) ENGINE = InnoDB,
 PARTITION p_future VALUES LESS THAN MAXVALUE ENGINE = InnoDB) */;

-- Data exporting was unselected.

-- Dumping structure for table db_face_recognation_v2.0.sn_mesin
CREATE TABLE IF NOT EXISTS `sn_mesin` (
  `sn` varchar(50) COLLATE utf8mb4_general_ci NOT NULL,
  `opd_id` int NOT NULL,
  `nama_lokasi` varchar(100) COLLATE utf8mb4_general_ci DEFAULT NULL,
  PRIMARY KEY (`sn`),
  KEY `opd_id` (`opd_id`),
  CONSTRAINT `sn_mesin_ibfk_1` FOREIGN KEY (`sn`) REFERENCES `devices` (`sn`) ON DELETE CASCADE,
  CONSTRAINT `sn_mesin_ibfk_2` FOREIGN KEY (`opd_id`) REFERENCES `master_opd` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table db_face_recognation_v2.0.users
CREATE TABLE IF NOT EXISTS `users` (
  `user_id` int NOT NULL AUTO_INCREMENT,
  `user_nip` varchar(50) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `user_pin` varchar(50) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `nama_lengkap` varchar(100) COLLATE utf8mb4_general_ci NOT NULL,
  `opd_id` int DEFAULT NULL,
  `role` enum('super_admin','admin_opd','asn') COLLATE utf8mb4_general_ci NOT NULL,
  `password_hash` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `is_face_registered` tinyint(1) DEFAULT '0',
  `approval_status` varchar(20) COLLATE utf8mb4_general_ci DEFAULT 'approved',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`),
  KEY `user_nip` (`user_nip`),
  KEY `user_pin` (`user_pin`),
  KEY `opd_id` (`opd_id`),
  CONSTRAINT `users_ibfk_1` FOREIGN KEY (`user_nip`) REFERENCES `data_pegawai` (`nip`) ON DELETE SET NULL,
  CONSTRAINT `users_ibfk_2` FOREIGN KEY (`user_pin`) REFERENCES `data_pegawai` (`pin`) ON DELETE SET NULL,
  CONSTRAINT `users_ibfk_3` FOREIGN KEY (`opd_id`) REFERENCES `master_opd` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB AUTO_INCREMENT=52 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table db_face_recognation_v2.0.user_akses_opd
CREATE TABLE IF NOT EXISTS `user_akses_opd` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_nip` varchar(50) COLLATE utf8mb4_general_ci NOT NULL,
  `opd_id` int NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `user_nip` (`user_nip`),
  KEY `opd_id` (`opd_id`),
  CONSTRAINT `user_akses_opd_ibfk_1` FOREIGN KEY (`user_nip`) REFERENCES `data_pegawai` (`nip`) ON DELETE CASCADE,
  CONSTRAINT `user_akses_opd_ibfk_2` FOREIGN KEY (`opd_id`) REFERENCES `master_opd` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

/*!40103 SET TIME_ZONE=IFNULL(@OLD_TIME_ZONE, 'system') */;
/*!40101 SET SQL_MODE=IFNULL(@OLD_SQL_MODE, '') */;
/*!40014 SET FOREIGN_KEY_CHECKS=IFNULL(@OLD_FOREIGN_KEY_CHECKS, 1) */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40111 SET SQL_NOTES=IFNULL(@OLD_SQL_NOTES, 1) */;
