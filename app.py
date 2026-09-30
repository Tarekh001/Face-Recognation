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
    print(f"Database PostgreSQL ({_db_host}:{_db_port}/{_db_name}) berhasil terhubung")

# =======================================================
# INI ADALAH BARIS YANG KEMUNGKINAN BESAR HILANG:
# Baris ini berfungsi mendaftarkan semua rute di routes.py
# =======================================================
app.register_blueprint(api_blueprint, url_prefix="/api")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)