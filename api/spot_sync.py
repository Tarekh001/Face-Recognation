import csv
import io
import os
import threading
import requests
from models import db, DataPegawai, UserAsn, PresensiAsn, AppSetting, get_wib_time


def is_valid_spot_pin(pin_val) -> bool:
    """SPOT ATTLOG accepts only numeric user PINs assigned by SPOT."""
    s = str(pin_val or "").strip()
    return bool(s) and s.isdigit()

DEFAULT_SPOT_BASE_URL = os.environ.get("SPOT_BASE_URL", "https://absen.meteoronyx.my.id")

# Prevents concurrent batch pushes between background cron runs and manual UI triggers.
SPOT_SYNC_LOCK = threading.Lock()

SPOT_SETTING_DEFAULTS = {
    "SPOT_BASE_URL": (DEFAULT_SPOT_BASE_URL, "URL server tujuan pengiriman log presensi SPOT"),
    "SPOT_OVERRIDE_SN": ("", "SN perangkat terpusat opsional jika server SPOT hanya memverifikasi satu SN"),
    "SPOT_CRON_ENABLED": ("true", "Status aktif penjadwal pengiriman otomatis Cron Job SPOT"),
    "SPOT_CRON_INTERVAL_MINUTES": ("5", "Interval eksekusi Cron Job sinkronisasi SPOT dalam menit"),
    "SPOT_AUTO_PUSH": ("true", "Kirim log presensi ASN secara langsung saat scan wajah berhasil"),
    "SPOT_STATUS_MODE": ("in_out", "Aturan kolom ke-3 Status ATTLOG: in_out (0/1), always_0 (0), atau auto_255 (255)"),
    "SPOT_VERIFY_MODE": ("15", "Aturan kolom ke-4 VerifyMode ATTLOG: 15 (Wajah) atau 1 (Sidik Jari)"),
    "SPOT_VALIDATION_VAL": ("0", "Nilai kolom ke-5 Validation pada payload ATTLOG"),
    "SPOT_WORKCODE_VAL": ("0", "Nilai kolom ke-6 WorkCode pada payload ATTLOG"),
    "SPOT_LAST_CRON_RUN": ("-", "Waktu terakhir Cron Job sinkronisasi SPOT dijalankan"),
    "SPOT_LAST_CRON_SUMMARY": ("Belum dijalankan", "Ringkasan hasil eksekusi Cron Job sinkronisasi SPOT terakhir"),
}


def ensure_spot_settings_seeded() -> None:
    changed = False
    for key, (val, desc) in SPOT_SETTING_DEFAULTS.items():
        if not AppSetting.query.get(key):
            db.session.add(AppSetting(setting_key=key, setting_value=val, description=desc))
            changed = True
    if changed:
        db.session.commit()


def _upsert_setting(key: str, value: str) -> None:
    row = AppSetting.query.get(key)
    desc = SPOT_SETTING_DEFAULTS.get(key, ("", ""))[1]
    if row:
        row.setting_value = str(value)
    else:
        db.session.add(AppSetting(setting_key=key, setting_value=str(value), description=desc))


def get_spot_config() -> dict:
    ensure_spot_settings_seeded()
    raw_interval = AppSetting.get("SPOT_CRON_INTERVAL_MINUTES", "5")
    try:
        interval_min = max(1, int(raw_interval))
    except ValueError:
        interval_min = 5

    return {
        "spot_base_url": (AppSetting.get("SPOT_BASE_URL", DEFAULT_SPOT_BASE_URL) or DEFAULT_SPOT_BASE_URL).strip(),
        "spot_override_sn": (AppSetting.get("SPOT_OVERRIDE_SN", "") or "").strip(),
        "spot_cron_enabled": str(AppSetting.get("SPOT_CRON_ENABLED", "true")).lower() in ("true", "1", "yes", "on"),
        "spot_cron_interval_minutes": interval_min,
        "spot_auto_push": str(AppSetting.get("SPOT_AUTO_PUSH", "true")).lower() in ("true", "1", "yes", "on"),
        "spot_status_mode": (AppSetting.get("SPOT_STATUS_MODE", "in_out") or "in_out").strip(),
        "spot_verify_mode": (AppSetting.get("SPOT_VERIFY_MODE", "15") or "15").strip(),
        "spot_validation_val": (AppSetting.get("SPOT_VALIDATION_VAL", "0") or "0").strip(),
        "spot_workcode_val": (AppSetting.get("SPOT_WORKCODE_VAL", "0") or "0").strip(),
        "spot_last_cron_run": AppSetting.get("SPOT_LAST_CRON_RUN", "-") or "-",
        "spot_last_cron_summary": AppSetting.get("SPOT_LAST_CRON_SUMMARY", "Belum dijalankan") or "Belum dijalankan",
    }


def update_spot_config(payload: dict) -> dict:
    mapping = {
        "spot_base_url": "SPOT_BASE_URL",
        "spot_override_sn": "SPOT_OVERRIDE_SN",
        "spot_cron_enabled": "SPOT_CRON_ENABLED",
        "spot_cron_interval_minutes": "SPOT_CRON_INTERVAL_MINUTES",
        "spot_auto_push": "SPOT_AUTO_PUSH",
        "spot_status_mode": "SPOT_STATUS_MODE",
        "spot_verify_mode": "SPOT_VERIFY_MODE",
        "spot_validation_val": "SPOT_VALIDATION_VAL",
        "spot_workcode_val": "SPOT_WORKCODE_VAL",
    }
    for json_key, setting_key in mapping.items():
        if json_key in payload and payload[json_key] is not None:
            val = payload[json_key]
            if isinstance(val, bool):
                val = "true" if val else "false"
            _upsert_setting(setting_key, str(val).strip())
    db.session.commit()
    return get_spot_config()


def format_attlog_line(
    presensi_asn_row: PresensiAsn,
    verify_mode: int = None,
    validation: int = None,
    work_code: int = None,
    config: dict = None,
) -> str:
    """
    Formats an ASN attendance record into the 6-column tab-separated ADMS ATTLOG line:
    {UserPIN}\\t{Time}\\t{Status}\\t{VerifyMode}\\t{Validation}\\t{WorkCode}
    """
    cfg = config or {}
    status_mode = str(cfg.get("spot_status_mode") or AppSetting.get("SPOT_STATUS_MODE", "in_out") or "in_out").strip()
    eff_verify = verify_mode if verify_mode is not None else (cfg.get("spot_verify_mode") or AppSetting.get("SPOT_VERIFY_MODE", "15") or "15")
    eff_valid = validation if validation is not None else (cfg.get("spot_validation_val") or AppSetting.get("SPOT_VALIDATION_VAL", "0") or "0")
    eff_work = work_code if work_code is not None else (cfg.get("spot_workcode_val") or AppSetting.get("SPOT_WORKCODE_VAL", "0") or "0")

    user_pin = str(presensi_asn_row.user_pin or "").strip()
    waktu_str = presensi_asn_row.waktu_scan.strftime("%Y-%m-%d %H:%M:%S")
    tipe = str(presensi_asn_row.tipe_absen or "IN").upper()

    if status_mode == "always_0":
        status_code = "0"
    elif status_mode == "auto_255":
        status_code = "255"
    else:
        status_code = "0" if tipe == "IN" else "1"

    return f"{user_pin}\t{waktu_str}\t{status_code}\t{eff_verify}\t{eff_valid}\t{eff_work}"


def build_spot_cdata_url(
    device_sn: str,
    base_url: str = DEFAULT_SPOT_BASE_URL,
    stamp: str = "9999",
) -> str:
    clean_base = (base_url or DEFAULT_SPOT_BASE_URL).rstrip("/")
    sn_val = (device_sn or "WEB_APP").strip()
    return f"{clean_base}/iclock/cdata?SN={sn_val}&table=ATTLOG&Stamp={stamp}"


def handshake_spot_device(
    device_sn: str,
    base_url: str = None,
    pushver: str = "2.4.1",
    timeout: int = 8,
) -> dict:
    effective_base = (base_url or AppSetting.get("SPOT_BASE_URL", DEFAULT_SPOT_BASE_URL)).rstrip("/")
    sn_val = (device_sn or "WEB_APP").strip()
    url = f"{effective_base}/iclock/cdata?SN={sn_val}&options=all&pushver={pushver}"
    try:
        resp = requests.get(url, timeout=timeout)
        body = (resp.text or "").strip()
        ok = (200 <= resp.status_code < 300) and ("GET OPTION FROM" in body.upper() or body.upper().startswith("OK"))
        return {
            "sn": sn_val,
            "ok": ok,
            "status_code": resp.status_code,
            "url": url,
            "response_text": body,
        }
    except Exception as exc:
        return {
            "sn": sn_val,
            "ok": False,
            "status_code": None,
            "url": url,
            "error": str(exc),
        }


def push_attlog_to_spot(
    presensi_asn_row: PresensiAsn,
    base_url: str = None,
    timeout: int = 8,
    commit: bool = True,
    override_sn: str = None,
    config: dict = None,
) -> dict:
    """
    Sends a single ASN attendance row to the SPOT ADMS endpoint.
    new-DBSPOT returns HTTP 200 even on rejected devices ("ERROR: Device not verified"),
    so body text must start with "OK" before marking the record as synced.
    """
    cfg = config or get_spot_config()
    effective_base = base_url or cfg.get("spot_base_url") or DEFAULT_SPOT_BASE_URL
    target_sn = (
        override_sn
        or cfg.get("spot_override_sn")
        or AppSetting.get("SPOT_DEVICE_SN")
        or presensi_asn_row.device_sn
    )
    url = build_spot_cdata_url(target_sn, base_url=effective_base)
    payload = format_attlog_line(presensi_asn_row, config=cfg)

    if not is_valid_spot_pin(presensi_asn_row.user_pin):
        err_msg = f"PIN SPOT '{presensi_asn_row.user_pin or '-'}' tidak valid (bukan numerik); periksa data_pegawai atau status Non-ASN."
        presensi_asn_row.spot_sync_status = "failed"
        presensi_asn_row.spot_synced_at = None
        presensi_asn_row.spot_response = err_msg
        if commit:
            db.session.commit()
        return {
            "ok": False,
            "status_code": 422,
            "device_sn": target_sn,
            "url": url,
            "payload": payload,
            "response_text": err_msg,
        }

    try:
        resp = requests.post(
            url,
            data=payload,
            headers={"Content-Type": "text/plain"},
            timeout=timeout,
        )
        body_text = (resp.text or "").strip()
        ok = (200 <= resp.status_code < 300) and body_text.upper().startswith("OK")
        presensi_asn_row.spot_sync_status = "synced" if ok else "failed"
        presensi_asn_row.spot_synced_at = get_wib_time() if ok else None
        presensi_asn_row.spot_response = f"HTTP {resp.status_code}: {body_text[:300]}"
        if commit:
            db.session.commit()
        return {
            "ok": ok,
            "status_code": resp.status_code,
            "device_sn": target_sn,
            "url": url,
            "payload": payload,
            "response_text": body_text,
        }
    except Exception as exc:
        presensi_asn_row.spot_sync_status = "failed"
        presensi_asn_row.spot_response = f"ERROR: {str(exc)[:300]}"
        if commit:
            db.session.commit()
        return {
            "ok": False,
            "status_code": None,
            "device_sn": target_sn,
            "url": url,
            "payload": payload,
            "error": str(exc),
        }


def sync_pending_batch(
    limit: int = 100,
    opd_id: int = None,
    include_failed: bool = True,
    base_url: str = None,
    trigger_source: str = "cron",
    commit: bool = True,
) -> dict:
    if not SPOT_SYNC_LOCK.acquire(blocking=False):
        return {
            "locked": True,
            "message": "Sinkronisasi SPOT sedang berjalan di proses lain.",
            "synced_count": 0,
            "failed_count": 0,
            "results": [],
        }

    try:
        cfg = get_spot_config()
        effective_base = (base_url or cfg["spot_base_url"]).strip()
        target_statuses = ["pending", "failed"] if include_failed else ["pending"]

        q = PresensiAsn.query.filter(PresensiAsn.spot_sync_status.in_(target_statuses))
        if opd_id:
            q = q.filter_by(opd_id=opd_id)

        pending_rows = q.order_by(PresensiAsn.waktu_scan.asc()).limit(min(int(limit or 100), 500)).all()
        synced_count = 0
        failed_count = 0
        results = []

        for row in pending_rows:
            res = push_attlog_to_spot(row, base_url=effective_base, commit=False, config=cfg)
            if res.get("ok"):
                synced_count += 1
            else:
                failed_count += 1
            results.append({
                "log_id": row.log_id,
                "nip": row.nip,
                "nama": row.nama_lengkap,
                "user_pin": row.user_pin,
                "ok": res.get("ok"),
                "status_code": res.get("status_code"),
                "payload": res.get("payload"),
                "response": res.get("response_text") or res.get("error"),
            })

        now_str = get_wib_time().strftime("%Y-%m-%d %H:%M:%S")
        summary_str = f"[{trigger_source.upper()}] {synced_count} terkirim, {failed_count} gagal (dari {len(pending_rows)} antrean)"
        _upsert_setting("SPOT_LAST_CRON_RUN", now_str)
        _upsert_setting("SPOT_LAST_CRON_SUMMARY", summary_str)

        if commit:
            db.session.commit()

        return {
            "locked": False,
            "message": f"Sinkronisasi SPOT selesai: {synced_count} berhasil, {failed_count} gagal.",
            "synced_count": synced_count,
            "failed_count": failed_count,
            "total_processed": len(pending_rows),
            "last_run": now_str,
            "summary": summary_str,
            "results": results,
        }
    finally:
        SPOT_SYNC_LOCK.release()


def push_attlog_to_spot_safe(presensi_asn_row: PresensiAsn) -> None:
    auto_push_flag = (
        os.environ.get("SPOT_AUTO_PUSH")
        or AppSetting.get("SPOT_AUTO_PUSH", "true")
        or "true"
    ).lower()
    if auto_push_flag in ("true", "1", "yes", "on"):
        push_attlog_to_spot(presensi_asn_row, commit=True)


def parse_spot_pegawai_csv(raw_text: str) -> list:
    """
    Parses SPOT employee CSV exports in either standard (`nip,nama,pin`)
    or outer-quoted SPOT format into `(nip, nama, pin)` tuples.
    """
    records = []
    seen = {}
    reader = csv.reader(io.StringIO(raw_text))
    for idx, row in enumerate(reader):
        if not row:
            continue
        inner = row[0] if len(row) == 1 else ",".join(row)
        try:
            parts = next(csv.reader([inner]))
        except StopIteration:
            continue
        if len(parts) < 3:
            continue
        nip = parts[0].strip()
        nama = parts[1].strip()
        pin = parts[2].strip()
        if idx == 0 and nip.lower() in ("nip", "nik"):
            continue
        if not nip or not pin:
            continue
        seen[nip] = (nip, nama or nip, pin)
    records.extend(seen.values())
    return records


def sync_pegawai_records_to_db(records: list) -> dict:
    """
    Upserts official ASN records into `data_pegawai` and repairs matching
    `users_asn.pin` and unsynced/mismatched `presensi_asn.user_pin` values.
    """
    existing = {dp.nip: dp for dp in DataPegawai.query.all()}
    next_id = max((dp.id or 0 for dp in existing.values()), default=0) + 1
    inserted = 0
    updated_pins = 0
    updated_names = 0
    to_add = []

    for nip, nama, pin in records:
        cur = existing.get(nip)
        if cur is None:
            to_add.append(DataPegawai(id=next_id, nip=nip, nama_lengkap=nama[:100], pin=pin[:50]))
            next_id += 1
            inserted += 1
        else:
            if (cur.pin or "").strip() != pin:
                cur.pin = pin[:50]
                updated_pins += 1
            if (cur.nama_lengkap or "").strip() != nama[:100]:
                cur.nama_lengkap = nama[:100]
                updated_names += 1

    if to_add:
        db.session.bulk_save_objects(to_add)
    db.session.flush()

    csv_pin_map = {nip: pin for nip, _nama, pin in records}
    synced_users_asn = 0
    for u in UserAsn.query.all():
        target_pin = csv_pin_map.get(u.nip)
        if target_pin and (u.pin or "").strip() != target_pin:
            u.pin = target_pin
            synced_users_asn += 1

    synced_presensi_asn = 0
    for pa in PresensiAsn.query.all():
        target_pin = csv_pin_map.get(pa.nip)
        if target_pin and (pa.user_pin or "").strip() != target_pin:
            pa.user_pin = target_pin
            if pa.spot_sync_status == "failed":
                pa.spot_sync_status = "pending"
                pa.spot_response = "PIN SPOT diperbarui dari CSV; siap dikirim ulang"
            synced_presensi_asn += 1

    db.session.commit()
    return {
        "total_csv_rows": len(records),
        "inserted_data_pegawai": inserted,
        "updated_pins": updated_pins,
        "updated_names": updated_names,
        "synced_users_asn": synced_users_asn,
        "synced_presensi_asn": synced_presensi_asn,
    }

