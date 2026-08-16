-- ==============================================
-- MIGRATION: Add per-device anti-spoofing toggle
-- Purpose: Move anti-spoofing from global setting
--          to per-device configuration for flexibility
--          in poor-lighting environments.
-- ==============================================

ALTER TABLE devices
ADD COLUMN anti_spoofing_enabled BOOLEAN NOT NULL DEFAULT TRUE;

-- Verify
SELECT sn, device_name, anti_spoofing_enabled FROM devices;
