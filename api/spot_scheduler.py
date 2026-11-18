import threading
import time
from datetime import datetime
from api.spot_sync import get_spot_config, sync_pending_batch
from models import get_wib_time


class SpotCronScheduler:
    def __init__(self, flask_app, check_interval_seconds: int = 30):
        self.app = flask_app
        self.check_interval_seconds = max(5, int(check_interval_seconds))
        self._stop_event = threading.Event()
        self._thread = None
        self._last_run_epoch = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="SpotCronScheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def run_once_if_due(self, force: bool = False) -> dict | None:
        with self.app.app_context():
            cfg = get_spot_config()
            if not force and not cfg.get("spot_cron_enabled", True):
                return None

            interval_sec = max(60, int(cfg.get("spot_cron_interval_minutes", 5)) * 60)
            now_epoch = time.time()
            if not force and (now_epoch - self._last_run_epoch) < interval_sec:
                return None

            self._last_run_epoch = now_epoch
            return sync_pending_batch(limit=100, include_failed=True, trigger_source="cron", commit=True)

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_once_if_due(force=False)
            except Exception as err:
                print(f"[SPOT-CRON] Peringatan eksekusi terjadwal: {err}")
            self._stop_event.wait(self.check_interval_seconds)


_active_scheduler: SpotCronScheduler | None = None


def start_spot_cron_scheduler(flask_app) -> SpotCronScheduler:
    global _active_scheduler
    if _active_scheduler is None:
        _active_scheduler = SpotCronScheduler(flask_app)
    _active_scheduler.start()
    return _active_scheduler
