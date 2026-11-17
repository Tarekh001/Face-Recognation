# SDD ledger - plan: d:\Project Diskominfo\project2\Face_Recognition_AI_Secure\plan_kerja2.0.md

Pre-flight:
- Task 1 -> Task 2: Task 1 creates `users_asn`, `users_non_asn`, `presensi_asn`, `presensi_non_asn` and updates `roster_jadwal_shift`; Task 2 maps SQLAlchemy models to those exact table and column names.
- Task 1 Ruling: `users_asn.nip` and `presensi_asn.nip` use `VARCHAR(50)` instead of `VARCHAR(18)` because `data_pegawai.nip` is `VARCHAR(50)` and contains operator row `admin001@kabtangerang.go.id` (27 chars) — matches `data_pegawai.nip` type — cost if wrong: one `ALTER COLUMN TYPE`.
- Task 1 Ruling: `presensi` has 37 valid ASN rows, 1 valid Non-ASN row, and 2 legacy orphan rows with `user_pin IS NULL` (`log_id` 31, 33); the 37 ASN rows migrate to `presensi_asn`, the 1 Non-ASN row migrates to `presensi_non_asn`, and all 40 rows remain preserved in `_legacy_presensi` — preserves 100% referential integrity in the new tables — cost if wrong: none (`_legacy_presensi` retains the 2 NULL rows).
Task 1: complete (tests: python scratch/test_migration_v2.py -> PASS 7/7 assertions)
Task 2: complete (tests: python scratch/test_models_v2.py -> PASS)
Task 3: complete (tests: python scratch/test_endpoints_v2.py -> PASS)
Task 4: complete (tests: python scratch/test_endpoints_v2.py -> PASS)
Task 5: complete (tests: python migrations/run_migration_v2.py --dry-run -> PASS)
Task 6: complete (tests: python scratch/test_spot_push.py -> PASS)
Final review: self-review (4/4 test suites green + frontend build green)
