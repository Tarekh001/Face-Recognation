import os
import warnings
from flask import Flask
from flask_cors import CORS
from api.routes import api_blueprint
from config.config import TEMP_DIR
from models import db

os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
warnings.filterwarnings("ignore", category=DeprecationWarning)
os.makedirs(TEMP_DIR, exist_ok=True)

app = Flask(__name__)
CORS(app)

# ── PostgreSQL Connection ──
# Di server: set environment variables DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
# Di lokal  : nilai default di bawah ini yang akan dipakai
_db_host = os.environ.get('DB_HOST', 'localhost')
_db_port = os.environ.get('DB_PORT', '5434')          # lokal pakai 5434
_db_name = os.environ.get('DB_NAME', 'db_face_recognation_v3.0')
_db_user = os.environ.get('DB_USER', 'postgres')
_db_pass = os.environ.get('DB_PASSWORD', 'apalah123')

app.config['SQLALCHEMY_DATABASE_URI'] = (
    f'postgresql+psycopg2://{_db_user}:{_db_pass}@{_db_host}:{_db_port}/{_db_name}'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-ganti-di-server')

db.init_app(app)

with app.app_context():
    # db.create_all()  # Dimatikan karena pakai skema SQL manual via DBeaver
    try:
        from sqlalchemy import text
        db.session.execute(text("ALTER TABLE presensi ADD COLUMN IF NOT EXISTS foto_presensi TEXT;"))
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS master_jam_kerja (
                id SERIAL PRIMARY KEY,
                nama_shift VARCHAR(100) NOT NULL,
                jam_masuk TIME NOT NULL,
                jam_pulang TIME NOT NULL,
                mulai_scan_masuk TIME NOT NULL,
                akhir_scan_masuk TIME NOT NULL,
                mulai_scan_pulang TIME NOT NULL,
                akhir_scan_pulang TIME NOT NULL,
                menit_toleransi INTEGER DEFAULT 0,
                is_lintas_hari BOOLEAN DEFAULT FALSE,
                abaikan_libur BOOLEAN DEFAULT FALSE,
                opd_id INTEGER REFERENCES master_opd(id) ON DELETE SET NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))
        db.session.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS jam_kerja_id INTEGER REFERENCES master_jam_kerja(id) ON DELETE SET NULL;"))
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS roster_jadwal_shift (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                tanggal DATE NOT NULL,
                jam_kerja_id INTEGER NOT NULL REFERENCES master_jam_kerja(id) ON DELETE RESTRICT,
                keterangan VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, tanggal)
            );
        """))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_roster_user_tanggal ON roster_jadwal_shift(user_id, tanggal);"))
        db.session.execute(text("ALTER TABLE presensi ADD COLUMN IF NOT EXISTS tanggal_tugas DATE;"))
        db.session.execute(text("ALTER TABLE presensi ADD COLUMN IF NOT EXISTS jam_kerja_id INTEGER REFERENCES master_jam_kerja(id) ON DELETE SET NULL;"))
        db.session.execute(text("UPDATE presensi SET tanggal_tugas = DATE(waktu_presensi) WHERE tanggal_tugas IS NULL;"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_presensi_tanggal_tugas ON presensi(tanggal_tugas);"))
        db.session.commit()

        # Auto-seed default MasterJamKerja profiles if empty
        from models import MasterJamKerja
        from datetime import time as time_type
        if MasterJamKerja.query.count() == 0:
            default_shifts = [
                MasterJamKerja(
                    nama_shift="Reguler ASN (5 Hari Kerja)",
                    jam_masuk=time_type(7, 30),
                    jam_pulang=time_type(16, 0),
                    mulai_scan_masuk=time_type(6, 0),
                    akhir_scan_masuk=time_type(12, 0),
                    mulai_scan_pulang=time_type(15, 0),
                    akhir_scan_pulang=time_type(20, 0),
                    menit_toleransi=30,
                    is_lintas_hari=False,
                    abaikan_libur=False,
                    opd_id=None,
                ),
                MasterJamKerja(
                    nama_shift="Shift Pagi Operasional",
                    jam_masuk=time_type(7, 0),
                    jam_pulang=time_type(15, 0),
                    mulai_scan_masuk=time_type(5, 30),
                    akhir_scan_masuk=time_type(10, 0),
                    mulai_scan_pulang=time_type(14, 0),
                    akhir_scan_pulang=time_type(18, 0),
                    menit_toleransi=15,
                    is_lintas_hari=False,
                    abaikan_libur=True,
                    opd_id=None,
                ),
                MasterJamKerja(
                    nama_shift="Shift Siang Operasional",
                    jam_masuk=time_type(14, 0),
                    jam_pulang=time_type(22, 0),
                    mulai_scan_masuk=time_type(12, 30),
                    akhir_scan_masuk=time_type(17, 0),
                    mulai_scan_pulang=time_type(21, 0),
                    akhir_scan_pulang=time_type(23, 59),
                    menit_toleransi=15,
                    is_lintas_hari=False,
                    abaikan_libur=True,
                    opd_id=None,
                ),
                MasterJamKerja(
                    nama_shift="Shift Malam (Lintas Hari)",
                    jam_masuk=time_type(21, 0),
                    jam_pulang=time_type(6, 0),
                    mulai_scan_masuk=time_type(19, 30),
                    akhir_scan_masuk=time_type(23, 59),
                    mulai_scan_pulang=time_type(5, 0),
                    akhir_scan_pulang=time_type(9, 0),
                    menit_toleransi=15,
                    is_lintas_hari=True,
                    abaikan_libur=True,
                    opd_id=None,
                ),
            ]
            db.session.add_all(default_shifts)
            db.session.commit()
            print("✅ [Schema] 4 Profil Master Jam Kerja default berhasil di-seed.")
    except Exception as _schema_err:
        db.session.rollback()
        print(f"⚠️ [Schema] Peringatan migrasi skema: {_schema_err}")
    print(f"Database PostgreSQL ({_db_host}:{_db_port}/{_db_name}) berhasil terhubung")

# =======================================================
# INI ADALAH BARIS YANG KEMUNGKINAN BESAR HILANG:
# Baris ini berfungsi mendaftarkan semua rute di routes.py
# =======================================================
app.register_blueprint(api_blueprint, url_prefix="/api")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
