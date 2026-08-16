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
# Format: postgresql+psycopg2://USER:PASSWORD@HOST:PORT/DATABASE
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql+psycopg2://postgres:apalah123@localhost:5434/db_face_recognation_v3.0'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

with app.app_context():
    # db.create_all()  # <-- KITA MATIKAN KARENA PAKAI RAW SQL / DBeaver
    print("Database PostgreSQL berhasil terhubung dan tabel siap digunakan")

# =======================================================
# INI ADALAH BARIS YANG KEMUNGKINAN BESAR HILANG:
# Baris ini berfungsi mendaftarkan semua rute di routes.py
# =======================================================
app.register_blueprint(api_blueprint, url_prefix="/api")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)