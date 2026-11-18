# SDD ledger - plan: d:\Project Diskominfo\project2\Face_Recognition_AI_Secure\plan_kerja2.1.md

Pre-flight:
- Task 1 -> Task 2: Task 1 provides `get_spot_config`, `update_spot_config`, `format_attlog_line`, `handshake_spot_device`, `sync_pending_batch`, and `SPOT_SYNC_LOCK` in `api/spot_sync.py` plus `SpotCronScheduler` in `api/spot_scheduler.py`; Task 2 exposes them via `/api/spot/status`, `/api/spot/config`, `/api/spot/logs`, `/api/spot/handshake-devices`, and `/api/spot/sync-pending`.
- Task 2 -> Task 3: Task 3 (`SpotSyncPage.jsx` and `DailyAttendanceReportView.jsx`) consumes the exact JSON keys produced by Task 2.
Task 1: complete (tests: python scratch/test_spot_scheduler_v21.py -> PASS)
Task 2: complete
Task 3: complete
