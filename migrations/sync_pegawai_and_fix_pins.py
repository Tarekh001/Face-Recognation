import argparse
import os
import shutil
import sys
from pathlib import Path
import psycopg2

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from api.spot_sync import parse_spot_pegawai_csv


def load_env_file(env_path: Path):
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def rename_biometric_artifacts(base_dir: Path, old_id: str, new_id: str, display_name: str, execute: bool) -> list:
    actions = []
    samples_old = base_dir / "samples" / old_id
    samples_new = base_dir / "samples" / new_id
    if samples_old.exists() and not samples_new.exists():
        actions.append(f"rename samples/{old_id} -> samples/{new_id}")
        if execute:
            samples_old.rename(samples_new)

    emb_old = base_dir / "samples_embedding" / old_id
    emb_new = base_dir / "samples_embedding" / new_id
    if emb_old.exists() and not emb_new.exists():
        actions.append(f"rename samples_embedding/{old_id} -> samples_embedding/{new_id}")
        if execute:
            emb_old.rename(emb_new)

    target_emb_dir = emb_new if emb_new.exists() else (emb_old if not execute and emb_old.exists() else None)
    if target_emb_dir is not None or (not execute and emb_old.exists()):
        old_pkl = (emb_new if execute else target_emb_dir or emb_old) / f"{old_id}.pkl"
        new_pkl = (emb_new if execute else target_emb_dir or emb_old) / f"{new_id}.pkl"
        old_txt = (emb_new if execute else target_emb_dir or emb_old) / f"{old_id}.txt"
        new_txt = (emb_new if execute else target_emb_dir or emb_old) / f"{new_id}.txt"

        if old_pkl.exists() and old_pkl != new_pkl and not new_pkl.exists():
            actions.append(f"rename {old_id}.pkl -> {new_id}.pkl")
            if execute:
                old_pkl.rename(new_pkl)

        txt_source = new_txt if new_txt.exists() else old_txt
        if txt_source.exists():
            actions.append(f"update {new_id}.txt -> [{new_id}, {display_name}]")
            if execute:
                if old_txt.exists() and old_txt != new_txt:
                    old_txt.unlink()
                new_txt.write_text(f"[{new_id}, {display_name}]\n", encoding="utf-8")
    return actions


def migrate_user_to_non_asn(cur, base_dir: Path, old_nip: str, target_nik: str, execute: bool, keep_admin_login_nip: str = None, keep_admin_pin: str = None):
    cur.execute(
        "SELECT user_id, nama_lengkap, opd_id, jam_kerja_id, is_face_registered, approval_status, created_at FROM public.users_asn WHERE nip = %s",
        (old_nip,),
    )
    row = cur.fetchone()
    if not row:
        print(f"  [SKIP] users_asn nip={old_nip} tidak ditemukan (mungkin sudah dimigrasi).")
        return

    uid, nama_lengkap, opd_id, jam_kerja_id, is_face_registered, approval_status, created_at = row
    eff_opd_id = opd_id or 1

    cur.execute("SELECT non_asn_id FROM public.users_non_asn WHERE nik = %s", (target_nik,))
    existing_na = cur.fetchone()
    if existing_na:
        non_asn_id = existing_na[0]
        print(f"  [INFO] users_non_asn nik={target_nik} sudah ada (non_asn_id={non_asn_id}).")
    else:
        print(f"  [PLAN] Insert users_non_asn: nik={target_nik}, nama='{nama_lengkap}', opd_id={eff_opd_id}")
        if execute:
            cur.execute(
                """
                INSERT INTO public.users_non_asn (nik, nama_lengkap, opd_id, jam_kerja_id, is_face_registered, approval_status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING non_asn_id
                """,
                (target_nik, nama_lengkap, eff_opd_id, jam_kerja_id, True if is_face_registered else False, approval_status, created_at),
            )
            non_asn_id = cur.fetchone()[0]
        else:
            non_asn_id = -1

    # Move attendance logs from presensi_asn -> presensi_non_asn
    cur.execute("SELECT COUNT(*) FROM public.presensi_asn WHERE user_id = %s", (uid,))
    log_cnt = cur.fetchone()[0]
    if log_cnt > 0:
        print(f"  [PLAN] Pindahkan {log_cnt} log presensi_asn (user_id={uid}) -> presensi_non_asn (nik={target_nik})")
        if execute:
            cur.execute(
                """
                INSERT INTO public.presensi_non_asn (
                    non_asn_id, nik, nama_lengkap, opd_id, jam_kerja_id,
                    tanggal_tugas, waktu_scan, tipe_absen, status_kehadiran,
                    keterlambatan_menit, device_sn, foto_presensi
                )
                SELECT
                    %s, %s, nama_lengkap, COALESCE(opd_id, %s), jam_kerja_id,
                    tanggal_tugas, waktu_scan, tipe_absen, status_kehadiran,
                    keterlambatan_menit, device_sn, foto_presensi
                FROM public.presensi_asn
                WHERE user_id = %s
                """,
                (non_asn_id, target_nik, eff_opd_id, uid),
            )
            cur.execute("DELETE FROM public.presensi_asn WHERE user_id = %s", (uid,))

    # Move roster entries if any
    cur.execute("SELECT COUNT(*) FROM public.roster_jadwal_shift WHERE user_id = %s", (uid,))
    roster_cnt = cur.fetchone()[0]
    if roster_cnt > 0:
        print(f"  [PLAN] Pindahkan {roster_cnt} roster user_id={uid} -> non_asn_id")
        if execute:
            cur.execute(
                "UPDATE public.roster_jadwal_shift SET non_asn_id = %s, user_id = NULL WHERE user_id = %s",
                (non_asn_id, uid),
            )

    # Rename biometric folders so /api/predict identifies them under users_non_asn
    disk_ops = rename_biometric_artifacts(base_dir, old_nip, target_nik, nama_lengkap, execute=execute)
    for op in disk_ops:
        print(f"  [DISK] {op}")

    if keep_admin_login_nip:
        # Preserve Web Admin login & FK relations while marking as pure operator account (is_face_registered=False)
        print(f"  [PLAN] Pertahankan akun login admin user_id={uid}: nip='{keep_admin_login_nip}', pin='{keep_admin_pin}', is_face_registered=False")
        if execute:
            cur.execute("SELECT 1 FROM public.data_pegawai WHERE nip = %s", (keep_admin_login_nip,))
            if cur.fetchone():
                cur.execute("UPDATE public.data_pegawai SET pin = %s WHERE nip = %s", (keep_admin_pin, keep_admin_login_nip))
            else:
                cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM public.data_pegawai")
                next_dp_id = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO public.data_pegawai (id, nip, nama_lengkap, pin) VALUES (%s, %s, %s, %s)",
                    (next_dp_id, keep_admin_login_nip, nama_lengkap, keep_admin_pin),
                )
            cur.execute("UPDATE public.users_asn SET nip = %s, pin = %s, is_face_registered = FALSE WHERE user_id = %s", (keep_admin_login_nip, keep_admin_pin, uid))
            cur.execute("UPDATE public.presensi_kegiatan SET nip = %s WHERE nip = %s", (keep_admin_login_nip, old_nip))
            cur.execute("DELETE FROM public.user_akses_opd WHERE user_nip IN (%s, %s)", (old_nip, keep_admin_login_nip))
            cur.execute("DELETE FROM public.data_pegawai WHERE nip = %s", (old_nip,))
    else:
        print(f"  [PLAN] Hapus user_id={uid} ({old_nip}) dari users_asn dan data_pegawai dummy-nya")
        if execute:
            cur.execute("DELETE FROM public.user_akses_opd WHERE user_nip = %s", (old_nip,))
            cur.execute("DELETE FROM public.users_asn WHERE user_id = %s", (uid,))
            cur.execute("DELETE FROM public.data_pegawai WHERE nip = %s", (old_nip,))


def main():
    parser = argparse.ArgumentParser(
        description="Sinkronisasi CSV Pegawai ASN (SPOT) & Perbaikan PIN/NIP Bermasalah"
    )
    parser.add_argument("--csv", required=True, help="Path ke file CSV export data pegawai SPOT")
    parser.add_argument("--env-file", default=None, help="Path file .env opsional (misal .env.server)")
    parser.add_argument("--port", type=int, default=None, help="Override port PostgreSQL (default 5434)")
    parser.add_argument("--dry-run", action="store_true", help="Simulasi tanpa mengubah DB maupun folder")
    parser.add_argument("--execute", action="store_true", help="Eksekusi perubahan ke DB PostgreSQL dan disk")
    args = parser.parse_args()

    execute = bool(args.execute and not args.dry_run)
    if args.env_file:
        load_env_file(ROOT_DIR / args.env_file)

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"ERROR: File CSV tidak ditemukan: {csv_path}")
        sys.exit(1)

    records = parse_spot_pegawai_csv(csv_path.read_text(encoding="utf-8-sig"))
    csv_map = {nip: (nama, pin) for nip, nama, pin in records}
    print(f"CSV parsed: {len(records)} ASN unik dari {csv_path}")
    print(f"Mode: {'EXECUTE' if execute else 'DRY-RUN'}")

    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=args.port or int(os.environ.get("DB_PORT", "5434")),
        dbname=os.environ.get("DB_NAME", "db_face_recognation_v3.0"),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", "apalah123"),
    )
    cur = conn.cursor()

    try:
        # 0. Ensure data_pegawai.id has an owned sequence if missing
        cur.execute("SELECT column_default FROM information_schema.columns WHERE table_schema='public' AND table_name='data_pegawai' AND column_name='id'")
        dp_def_row = cur.fetchone()
        if dp_def_row and dp_def_row[0] is None:
            print("[Step 0] Memasang sequence DEFAULT nextval('public.data_pegawai_id_seq') pada data_pegawai.id")
            if execute:
                cur.execute("CREATE SEQUENCE IF NOT EXISTS public.data_pegawai_id_seq")
                cur.execute("SELECT setval('public.data_pegawai_id_seq', COALESCE((SELECT MAX(id) FROM public.data_pegawai), 1), true)")
                cur.execute("ALTER TABLE public.data_pegawai ALTER COLUMN id SET DEFAULT nextval('public.data_pegawai_id_seq')")

        # 1. Upsert data_pegawai from official SPOT CSV
        cur.execute("SELECT COALESCE(MAX(id), 0) FROM public.data_pegawai")
        next_dp_id = cur.fetchone()[0] + 1
        cur.execute("SELECT nip, nama_lengkap, pin FROM public.data_pegawai")
        existing_dp = {r[0]: (r[1], r[2]) for r in cur.fetchall()}

        inserted_dp = 0
        updated_pin_dp = 0
        updated_name_dp = 0
        for nip, nama, pin in records:
            if nip not in existing_dp:
                inserted_dp += 1
                if execute:
                    cur.execute(
                        "INSERT INTO public.data_pegawai (id, nip, nama_lengkap, pin) VALUES (%s, %s, %s, %s)",
                        (next_dp_id, nip, nama[:100], pin[:50]),
                    )
                    next_dp_id += 1
            else:
                old_nama, old_pin = existing_dp[nip]
                if str(old_pin or "").strip() != pin:
                    updated_pin_dp += 1
                if str(old_nama or "").strip() != nama[:100]:
                    updated_name_dp += 1
                if execute and (str(old_pin or "").strip() != pin or str(old_nama or "").strip() != nama[:100]):
                    cur.execute(
                        "UPDATE public.data_pegawai SET pin = %s, nama_lengkap = %s WHERE nip = %s",
                        (pin[:50], nama[:100], nip),
                    )
        print(f"[Step 1] data_pegawai CSV sync: insert={inserted_dp}, update_pin={updated_pin_dp}, update_nama={updated_name_dp}")

        # 2. Repair registered ASN accounts whose NIP was previously NIK+00
        nik00_to_real_asn = [
            ("360303580302000700", "200203182025212001"),  # NINA SETYAWATI -> PIN 14667
            ("360303700896000300", "199608302025212058"),  # SYLVIA IRAWAN WINATA PUTRI -> PIN 15564
        ]
        print("\n[Step 2] Perbaikan NIP & PIN ASN Asli yang ditemukan di CSV baru:")
        for old_nip, new_nip in nik00_to_real_asn:
            if new_nip not in csv_map:
                print(f"  [SKIP] Target NIP {new_nip} tidak ditemukan di CSV.")
                continue
            real_nama, real_pin = csv_map[new_nip]
            cur.execute("SELECT user_id, nama_lengkap, pin FROM public.users_asn WHERE nip = %s", (old_nip,))
            u = cur.fetchone()
            if not u:
                print(f"  [SKIP] old_nip={old_nip} tidak ditemukan di users_asn (mungkin sudah diperbaiki).")
                continue
            uid, db_nama, db_pin = u
            print(f"  [FIX] user_id={uid} '{db_nama}': {old_nip} ({db_pin}) -> {new_nip} (PIN {real_pin})")
            disk_ops = rename_biometric_artifacts(ROOT_DIR, old_nip, new_nip, db_nama, execute=execute)
            for op in disk_ops:
                print(f"    [DISK] {op}")
            if execute:
                cur.execute(
                    "UPDATE public.users_asn SET nip = %s, pin = %s WHERE user_id = %s",
                    (new_nip, real_pin, uid),
                )
                cur.execute("UPDATE public.presensi_asn SET nip = %s, user_pin = %s WHERE user_id = %s", (new_nip, real_pin, uid))
                cur.execute("UPDATE public.presensi_kegiatan SET nip = %s WHERE nip = %s", (new_nip, old_nip))
                cur.execute("DELETE FROM public.data_pegawai WHERE nip = %s", (old_nip,))

        # 3. Sync users_asn.pin & presensi_asn.user_pin for all existing ASN matching CSV (e.g., Diaz Mardiwibowo -> 97)
        print("\n[Step 3] Sinkronisasi PIN seluruh users_asn & presensi_asn terhadap CSV:")
        cur.execute("SELECT user_id, nip, pin, nama_lengkap FROM public.users_asn")
        fixed_u_pins = 0
        for uid, nip, u_pin, u_nama in cur.fetchall():
            if nip in csv_map:
                real_nama, real_pin = csv_map[nip]
                if str(u_pin or "").strip() != real_pin:
                    fixed_u_pins += 1
                    print(f"  [PIN FIX] user_id={uid} {nip} ({u_nama}): '{u_pin}' -> '{real_pin}'")
                    if execute:
                        cur.execute("UPDATE public.users_asn SET pin = %s WHERE user_id = %s", (real_pin, uid))
                        cur.execute(
                            "UPDATE public.presensi_asn SET user_pin = %s WHERE user_id = %s",
                            (real_pin, uid),
                        )
        print(f"  Total users_asn PIN diperbaiki langsung: {fixed_u_pins}")

        # 4. Migrate Non-ASN / Tenaga Ahli / Unknown-NIK+00 / Magang+Admin out of ASN queue
        print("\n[Step 4] Pemisahan akun Non-ASN / Tenaga Ahli / Magang-Admin:")
        migrate_user_to_non_asn(cur, ROOT_DIR, old_nip="123631216161316132", target_nik="1236312161613161", execute=execute)
        migrate_user_to_non_asn(cur, ROOT_DIR, old_nip="360308490385000400", target_nik="3603084903850004", execute=execute)
        migrate_user_to_non_asn(
            cur,
            ROOT_DIR,
            old_nip="031188791093271576",
            target_nik="0311887910932715",
            execute=execute,
            keep_admin_login_nip="admin01.diskominfo@kabtangerang.go.id",
            keep_admin_pin="ADM-031188",
        )

        # 5. Clean orphan dummy rows in data_pegawai & samples_embedding/9999999999999991
        print("\n[Step 5] Pembersihan data yatim uji coba:")
        for orphan_nip in ("9999999999999991", "admin.kominfo@kabtangerang.go.id"):
            cur.execute("SELECT COUNT(*) FROM public.users_asn WHERE nip = %s", (orphan_nip,))
            used_u = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM public.presensi_asn WHERE nip = %s", (orphan_nip,))
            used_p = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM public.presensi_kegiatan WHERE nip = %s", (orphan_nip,))
            used_k = cur.fetchone()[0]
            if used_u == 0 and used_p == 0 and used_k == 0:
                cur.execute("SELECT id, nama_lengkap, pin FROM public.data_pegawai WHERE nip = %s", (orphan_nip,))
                dp_hit = cur.fetchone()
                if dp_hit:
                    print(f"  [CLEAN] Hapus data_pegawai yatim: {dp_hit}")
                    if execute:
                        cur.execute("DELETE FROM public.data_pegawai WHERE nip = %s", (orphan_nip,))
                orphan_emb_dir = ROOT_DIR / "samples_embedding" / orphan_nip
                if orphan_emb_dir.exists():
                    print(f"  [CLEAN DISK] Hapus folder embedding yatim: {orphan_emb_dir}")
                    if execute:
                        shutil.rmtree(orphan_emb_dir)

        if execute:
            cur.execute("SELECT setval('public.data_pegawai_id_seq', COALESCE((SELECT MAX(id) FROM public.data_pegawai), 1), true)")
            cur.execute("SELECT setval(pg_get_serial_sequence('public.users_non_asn', 'non_asn_id'), COALESCE((SELECT MAX(non_asn_id) FROM public.users_non_asn), 1), true)")
            cur.execute("SELECT setval(pg_get_serial_sequence('public.presensi_non_asn', 'log_id'), COALESCE((SELECT MAX(log_id) FROM public.presensi_non_asn), 1), true)")
            conn.commit()
            print("\nSUCCESS: Perubahan database & folder biometrik telah disimpan permanen.")
        else:
            conn.rollback()
            print("\nDRY-RUN SELESAI: Tidak ada perubahan ditulis ke DB atau disk. Jalankan dengan --execute untuk menerapkan.")

    except Exception as exc:
        conn.rollback()
        print(f"\nERROR: Rollback transaksi karena: {exc}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
