import argparse
import os
import sys
from pathlib import Path
import psycopg2


def load_env_file(env_path: Path):
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def main():
    parser = argparse.ArgumentParser(
        description="Migration Runner v2.0: Split ASN & Non-ASN Tables (Local & Server)"
    )
    parser.add_argument("--env-file", default=".env", help="Path to .env or .env.server file")
    parser.add_argument("--dry-run", action="store_true", help="Inspect database state without modifying")
    parser.add_argument("--execute", action="store_true", help="Execute migrate_v2_split_asn_non_asn.sql")
    args = parser.parse_args()

    root_dir = Path(__file__).resolve().parent.parent
    load_env_file(root_dir / args.env_file)

    db_host = os.environ.get("DB_HOST", "localhost")
    db_port = int(os.environ.get("DB_PORT", "5434"))
    db_name = os.environ.get("DB_NAME", "db_face_recognation_v3.0")
    db_user = os.environ.get("DB_USER", "postgres")
    db_pass = os.environ.get("DB_PASSWORD", "apalah123")

    sql_path = Path(__file__).resolve().parent / "migrate_v2_split_asn_non_asn.sql"
    if not sql_path.exists():
        print(f"ERROR: SQL file not found at {sql_path}")
        sys.exit(1)

    conn = psycopg2.connect(
        host=db_host, port=db_port, dbname=db_name, user=db_user, password=db_pass
    )
    cur = conn.cursor()

    print(f"Connected to PostgreSQL: {db_host}:{db_port}/{db_name}")
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name;
        """
    )
    public_tables = [r[0] for r in cur.fetchall()]
    print(f"Current public tables ({len(public_tables)}): {', '.join(public_tables)}")

    if args.execute and not args.dry_run:
        print("Executing migration SQL: migrate_v2_split_asn_non_asn.sql ...")
        cur.execute(sql_path.read_text(encoding="utf-8"))
        conn.commit()
        print("Migration committed successfully.")

    for tbl in ("users_asn", "users_non_asn", "presensi_asn", "presensi_non_asn"):
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = %s
            );
            """,
            (tbl,),
        )
        exists = cur.fetchone()[0]
        if exists:
            cur.execute(f'SELECT COUNT(*) FROM public."{tbl}";')
            cnt = cur.fetchone()[0]
            print(f"  [OK] public.{tbl}: {cnt} rows")
        else:
            print(f"  [PENDING] public.{tbl}: not created yet")

    conn.close()


if __name__ == "__main__":
    main()
