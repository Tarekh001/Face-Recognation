import uuid
import os
import pickle
import math
import jwt
import shutil
from models import db, User, Presensi, MasterOpd, AuditLog, Device, SnMesin, UserAksesOpd, DataPegawai, UserAdmin, AppSetting, HariLiburCustom, JadwalKegiatan, UndanganKegiatan, PresensiKegiatan
from functools import wraps
from flask import Blueprint, request, jsonify
from api.facenet_utils import get_embedding, get_embeddings, compare_faces, read_txt, is_valid_image, register_user_and_generate_embeddings
from config.config import EMBEDDINGS_DIR, TEMP_DIR, THRESHOLD
from uuid import uuid4
from datetime import datetime, timedelta, date as date_type, time as time_type
import pytz
from werkzeug.security import generate_password_hash
# pyrefly: ignore [missing-import]
import holidays

api_blueprint = Blueprint("api", __name__)
SECRET_KEY = "diskominfo_tangerang_secret_key"

# ==========================================
# HELPER FUNCTIONS
# ==========================================
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def get_wib_time():
    tz = pytz.timezone('Asia/Jakarta')
    return datetime.now(tz)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def calculate_haversine(lat1, lon1, lat2, lon2):
    """
    Hitung jarak antara dua titik koordinat menggunakan rumus Haversine.
    Input: latitude & longitude dalam derajat desimal.
    Output: jarak dalam meter.
    """
    R = 6371000  # Radius bumi dalam meter
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def str_to_bool(val):
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ('true', '1', 't', 'y', 'yes')
    if isinstance(val, int):
        return bool(val)
    return False

def catat_audit(actor_id, action, target_table, keterangan, target_record_id="-", ip_address=None, auto_commit=True):
    from models import AuditLog
    if ip_address is None:
        try:
            ip_address = request.remote_addr
        except Exception:
            ip_address = None
    log = AuditLog(
        actor_user_id=actor_id, 
        action=action, 
        target_table=target_table, 
        target_record_id=str(target_record_id), 
        ip_address=ip_address,
        keterangan_detail=keterangan
    )
    db.session.add(log)
    if auto_commit:
        db.session.commit()

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'message': 'Token tidak ditemukan!'}), 401
        try:
            data = jwt.decode(token.split(" ")[1], SECRET_KEY, algorithms=["HS256"])
            current_user = User.query.filter_by(nip=data['nip']).first()
        except:
            return jsonify({'message': 'Token tidak valid atau kedaluwarsa!'}), 401
        return f(current_user, *args, **kwargs)
    return decorated

# ==========================================
# 1. INISIALISASI SUPER ADMIN
# ==========================================
@api_blueprint.route('/init-super-admin', methods=['GET'])
def init_super_admin():
    from models import DataPegawai

    opd = MasterOpd.query.filter_by(kode_opd="OPD-001").first()
    if not opd:
        opd = MasterOpd(nama_opd="Dinas Komunikasi dan Informatika", kode_opd="OPD-001")
        db.session.add(opd)
        db.session.commit()

    super_admin_username = "admin001@kabtangerang.go.id"
    pegawai = DataPegawai.query.filter_by(nip=super_admin_username).first()
    if not pegawai:
        pegawai = DataPegawai(
            pin="PIN-ADMIN-01", 
            nip=super_admin_username,
            nama_lengkap="Super Admin Diskominfo"
        )
        db.session.add(pegawai)
        db.session.commit()

    admin = User.query.filter_by(nip=super_admin_username).first()
    if not admin:
        admin = User(
            nip=super_admin_username,
            pin=pegawai.pin,
            nama_lengkap="Super Admin Diskominfo",
            username=super_admin_username,
            opd_id=opd.id,
            role="super_admin",
            password_hash=generate_password_hash("adminanakmagangumn")
        )
        db.session.add(admin)
        db.session.commit()
        
        catat_audit(admin.id, "SYSTEM_INIT", "users", "Inisialisasi akun Super Admin berhasil dilakukan.")

    # Auto-register device default untuk Web Dashboard (agar predict tidak 403)
    web_device = Device.query.get("WEB_APP_01")
    if not web_device:
        web_device = Device(
            sn="WEB_APP_01",
            name="Web Dashboard",
            device_name="Browser",
            platform="Web",
            timezone="Asia/Jakarta",
            verified=True,
        )
        db.session.add(web_device)
        # Pemetaan ke OPD Diskominfo
        web_mapping = SnMesin.query.get("WEB_APP_01")
        if not web_mapping:
            web_mapping = SnMesin(sn="WEB_APP_01", opd_id=opd.id, nama_lokasi="Web Dashboard")
            db.session.add(web_mapping)
        db.session.commit()

    if admin.created_at and (datetime.utcnow() - admin.created_at).total_seconds() < 10:
        return jsonify({"message": "✅ Akun Super Admin dan Instansi Diskominfo berhasil dibuat!"}), 201

    return jsonify({"message": "⚠️ Akun Super Admin sudah ada di database."}), 200

# ==========================================
# 2. LOGIN
# ==========================================
@api_blueprint.route('/login', methods=['POST'])
def login():
    auth = request.form if request.form else request.get_json()
    if not auth or not auth.get('username') or not auth.get('password'):
        return jsonify({"message": "Username dan Password wajib diisi!"}), 400

    # Login menggunakan field `username` (bukan NIP)
    user = User.query.filter_by(username=auth.get('username')).first()

    # Fallback: coba cari berdasarkan NIP (backward-compatible dengan akun lama)
    if not user:
        user = User.query.filter_by(nip=auth.get('username')).first()

    if not user:
        return jsonify({"message": "User tidak ditemukan!"}), 404
    if user.role == 'asn':
        return jsonify({"message": "Akses ditolak! ASN tidak memiliki hak akses dashboard."}), 403

    if user.check_password(auth.get('password')):
        token = jwt.encode({
            'nip': user.nip,
            'role': user.role,
            'exp': datetime.utcnow() + timedelta(minutes=15)
        }, SECRET_KEY, algorithm="HS256")

        return jsonify({
            "message": "Login Berhasil",
            "access_token": token,
            "user": {
                "nama": user.nama_lengkap,
                "role": user.role,
                "nip": user.nip,
                "username": user.username,
                "opd_id": user.opd_id,
            }
        }), 200

    return jsonify({"message": "Password salah!"}), 401

# ==========================================
# 2b. ANTI-SPOOFING CHECK (Multi-Frame Temporal)
# ==========================================
from api.anti_spoofing_utils import spoof_checker

@api_blueprint.route('/check-spoof', methods=['POST'])
def check_spoof():
    """
    Multi-frame anti-spoofing — analisis temporal dari 3+ frame berurutan.
    
    Flutter kiosk mengirim 3 snapshot yang diambil ~200ms interval.
    Server menganalisis PERUBAHAN antar frame untuk mendeteksi:
      - Foto cetak (zero motion)
      - Layar digital (screen flicker pattern)
      - Wajah asli (micro-movement alami)
    
    Request: multipart/form-data
      - device_sn: serial number perangkat (wajib)
      - frame_0, frame_1, frame_2: 3 foto berurutan (JPG)
      - ATAU: photo (single frame, backward compatible)
    
    Response 200:
      { "is_real": bool, "confidence": float, "label": str }
    """
    temp_paths = []
    
    try:
        # ── Check device-level anti-spoofing setting ──
        device_sn = request.form.get('device_sn', '')
        if device_sn:
            device = Device.query.get(device_sn)
            if device and not device.anti_spoofing_enabled:
                print(f"\n🛡️ [Anti-Spoof] BYPASS — Anti-spoofing disabled for device: {device_sn}")
                return jsonify({
                    "is_real": True,
                    "confidence": 1.0,
                    "threshold": spoof_checker.threshold,
                    "label": "REAL",
                    "frames_analyzed": 0,
                    "message": "Bypass by device config"
                }), 200

        # Mode 1: Multi-frame (preferred)
        frame_keys = sorted([k for k in request.files.keys() if k.startswith('frame_')])
        
        if len(frame_keys) >= 2:
            # Multi-frame mode
            for key in frame_keys:
                f = request.files[key]
                temp_path = os.path.join(TEMP_DIR, f"spoof_{uuid4().hex}.jpg")
                f.save(temp_path)
                temp_paths.append(temp_path)
            
            res = spoof_checker.check_liveness_multi(temp_paths)
            if len(res) == 3:
                is_real, confidence, label = res
            else:
                is_real, confidence = res
                label = "REAL" if is_real else "SPOOF"
            
        elif 'photo' in request.files:
            # Single-frame fallback
            photo = request.files['photo']
            temp_path = os.path.join(TEMP_DIR, f"spoof_{uuid4().hex}.jpg")
            photo.save(temp_path)
            temp_paths.append(temp_path)
            
            res = spoof_checker.check_liveness(temp_path)
            if len(res) == 3:
                is_real, confidence, label = res
            else:
                is_real, confidence = res
                label = "REAL" if is_real else "SPOOF"
        else:
            return jsonify({"error": "Kirim frame_0/frame_1/frame_2 atau photo"}), 400

        return jsonify({
            "is_real": is_real,
            "confidence": round(confidence, 4),
            "threshold": spoof_checker.threshold,
            "label": label,
            "frames_analyzed": len(temp_paths),
        }), 200

    except Exception as e:
        print(f"[Anti-Spoof API] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "is_real": True, "confidence": 0.0,
            "label": "BYPASS",
            "warning": str(e),
        }), 200

    finally:
        for p in temp_paths:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass


# ==========================================
# 3. PREDICT Wajah (PERBAIKAN user_pin)
# ==========================================
@api_blueprint.route('/predict', methods=['POST'])
def predict():
    if 'photo' not in request.files:
        return jsonify({"error": "Image file is required"}), 400

    # ── GLOBAL DEVICE INTERCEPTOR ── (di awal fungsi)
    device_klien_sn = request.form.get("device_sn", "WEB_APP_01")
    device = Device.query.get(device_klien_sn)
    if not device or not device.verified or device.opd_id is None:
        return jsonify({
            "error": "DeviceUnbound",
            "message": "Perangkat telah diputus aksesnya oleh server. Silakan aktivasi ulang."
        }), 403

    # ── WORKING DAY VALIDATION (Dynamic from DB) ──
    now_dt = datetime.now()
    today_date = now_dt.date()
    current_time = now_dt.time()

    # Cek akhir pekan
    if today_date.weekday() >= 5:
        hari = "Sabtu" if today_date.weekday() == 5 else "Minggu"
        print(f"\n🚫 [PREDICT] DITOLAK — Hari libur akhir pekan ({hari}) | Device: {device_klien_sn}")
        return jsonify({"error": f"Presensi ditolak: Hari Libur Akhir Pekan ({hari}).", "reason": "WEEKEND"}), 403

    # Cek hari libur CUSTOM (cuti bersama, dll) — prioritas pertama
    libur_custom = HariLiburCustom.query.filter_by(tanggal=today_date).first()
    if libur_custom:
        print(f"\n🚫 [PREDICT] DITOLAK — Hari libur custom: {libur_custom.keterangan} | Device: {device_klien_sn}")
        return jsonify({
            "error": f"Presensi ditolak: {libur_custom.keterangan}.",
            "reason": "CUSTOM_HOLIDAY", "holiday_name": libur_custom.keterangan
        }), 403

    # Cek hari libur nasional Indonesia (fallback)
    id_holidays = holidays.Indonesia(years=today_date.year)
    if today_date in id_holidays:
        nama_libur = id_holidays.get(today_date)
        print(f"\n🚫 [PREDICT] DITOLAK — Hari libur nasional: {nama_libur} | Device: {device_klien_sn}")
        return jsonify({
            "error": f"Presensi ditolak: Hari Libur Nasional — {nama_libur}.",
            "reason": "HOLIDAY", "holiday_name": nama_libur
        }), 403

    photo = request.files['photo']
    if not allowed_file(photo.filename):
        return jsonify({"error": "File type not allowed."}), 400

    temp_filename = f"{uuid4().hex}.jpg"
    image_path = os.path.join(TEMP_DIR, temp_filename)
    photo.save(image_path)

    test_embedding, test_embedding_flip = get_embeddings(image_path)
    #os.remove(image_path)

    if test_embedding is None:
        return jsonify({"error": "Failed to extract face embedding"}), 500

    best_nip, best_name, best_similarity = "unknown", "unknown", 0.0

    for folder_name in os.listdir(EMBEDDINGS_DIR):
        pkl_path = os.path.join(EMBEDDINGS_DIR, folder_name, f"{folder_name}.pkl")
        txt_path = os.path.join(EMBEDDINGS_DIR, folder_name, f"{folder_name}.txt")

        if not os.path.exists(pkl_path) or not os.path.exists(txt_path):
            continue

        with open(pkl_path, "rb") as f:
            known_embeddings = pickle.load(f)

        similarity = compare_faces(test_embedding, known_embeddings, THRESHOLD, test_embedding_flip)
        if similarity > best_similarity:
            best_similarity = similarity
            best_nip, best_name = read_txt(txt_path)

    if best_nip != "unknown" and best_similarity >= THRESHOLD:
        similarity_pct = float(round(best_similarity * 100, 1))
        user = User.query.filter_by(nip=best_nip).first()
        if user:
            # ── Cek Approval Status ──
            if user.approval_status == 'pending':
                print(f"\n🟡 [FACE-AI] PENDING: {user.nama_lengkap} (NIP: {best_nip}) | Similarity: {similarity_pct}% | Menunggu persetujuan Admin")
                return jsonify({"error": "Akun Anda sedang menunggu persetujuan Admin."}), 403
            if user.approval_status == 'rejected':
                print(f"\n🔴 [FACE-AI] REJECTED: {user.nama_lengkap} (NIP: {best_nip}) | Registrasi ditolak oleh Admin")
                return jsonify({"error": "Registrasi Anda telah ditolak oleh Admin."}), 403

            # Update statistik device
            device.last_activity = get_wib_time()
            device.transaction_count = (device.transaction_count or 0) + 1

            # ── OFFLINE-READY: Accept local_timestamp from Store-and-Forward ──
            is_offline_sync = False
            local_ts_raw = request.form.get('local_timestamp')
            if local_ts_raw:
                try:
                    # Parse ISO8601 dari Flutter (e.g. "2026-06-29T08:05:30.000+07:00")
                    parsed_ts = datetime.fromisoformat(local_ts_raw.replace('Z', '+00:00'))
                    # Konversi ke WIB jika belum
                    wib = pytz.timezone('Asia/Jakarta')
                    if parsed_ts.tzinfo is None:
                        now = wib.localize(parsed_ts)
                    else:
                        now = parsed_ts.astimezone(wib)
                    is_offline_sync = True
                    print(f"📶 [OFFLINE-SYNC] Using local_timestamp: {now.strftime('%Y-%m-%d %H:%M:%S')} (from kiosk)")
                except Exception as ts_err:
                    print(f"⚠️ [OFFLINE-SYNC] Invalid local_timestamp '{local_ts_raw}': {ts_err} — fallback to server time")
                    now = get_wib_time()
            else:
                now = get_wib_time()

            today = now.date()
            status_absen = None

            # ── Dynamic Working Hours from DB ──
            def parse_time(val, fallback_h, fallback_m=0):
                try:
                    parts = val.strip().split(':')
                    return time_type(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)
                except Exception:
                    return time_type(fallback_h, fallback_m)

            jam_masuk_mulai  = parse_time(AppSetting.get('JAM_MASUK_MULAI',  '06:00:00'), 6)
            jam_masuk_akhir  = parse_time(AppSetting.get('JAM_MASUK_AKHIR',  '12:00:00'), 12)
            batas_terlambat  = parse_time(AppSetting.get('BATAS_TERLAMBAT',  '08:00:00'), 8)
            jam_keluar_mulai = parse_time(AppSetting.get('JAM_KELUAR_MULAI', '15:00:00'), 15)
            jam_keluar_akhir = parse_time(AppSetting.get('JAM_KELUAR_AKHIR', '20:00:00'), 20)

            ct = now.time()
            if jam_masuk_mulai <= ct < jam_masuk_akhir:
                status_absen = "IN"
            elif jam_keluar_mulai <= ct < jam_keluar_akhir:
                status_absen = "OUT"
            else:
                print(f"\n🟡 [FACE-AI] OUT OF HOURS: {user.nama_lengkap} (NIP: {best_nip}) | Similarity: {similarity_pct}% | Waktu: {now.strftime('%H:%M:%S')}")
                print(f"   ↳ Dikenali tapi di luar jam presensi ({jam_masuk_mulai.strftime('%H:%M')}-{jam_masuk_akhir.strftime('%H:%M')} / {jam_keluar_mulai.strftime('%H:%M')}-{jam_keluar_akhir.strftime('%H:%M')})\n")
                return jsonify({"message": f"Maaf {user.nama_lengkap}, sekarang bukan jam presensi ASN."}), 403
                # # ── BYPASS SEMENTARA: Hilangkan batasan range waktu presensi untuk testing ──
                # # Mengizinkan presensi kapan saja saat masa pengujian/demo.
                # # Sebelum jam 13:00 dialokasikan 'IN', setelah jam 13:00 dialokasikan 'OUT'.
                # status_absen = "IN" if ct < time_type(13, 0) else "OUT"
                # print(f"\nℹ️ [FACE-AI] Bypass Range Waktu: {user.nama_lengkap} (NIP: {best_nip}) otomatis dialokasikan '{status_absen}' (Waktu: {now.strftime('%H:%M:%S')})")

            # ── Attendance identifier: use AI-recognized NIP/NIK (best_nip) directly ──
            # best_nip is ALWAYS populated here — it came from the face embedding match.
            # This avoids NULL issues from user.pin (Non-ASN) or FK-nullified user.nip.
            attendance_id = best_nip

            # 2. Validasi: Cek apakah user sudah absen hari ini
            existing_log = Presensi.query.filter(
                Presensi.user_pin == attendance_id,
                db.func.date(Presensi.waktu_scan) == today,
                Presensi.tipe_absen == status_absen
            ).first()

            if existing_log:
                print(f"\n🟡 [FACE-AI] DUPLICATE: {user.nama_lengkap} (NIP: {best_nip}) | Similarity: {similarity_pct}% | Sudah {status_absen} hari ini\n")
                return jsonify({"message": f"Anda sudah melakukan presensi {status_absen} hari ini."}), 400

            # 3. Hitung Keterlambatan (Dynamic — hanya sesi IN)
            status_kehadiran = "ON_TIME"
            keterlambatan_menit = 0

            if status_absen == "IN":
                batas_dt = now.replace(hour=batas_terlambat.hour, minute=batas_terlambat.minute, second=0, microsecond=0)
                if now > batas_dt:
                    status_kehadiran = "LATE"
                    delta = now - batas_dt
                    keterlambatan_menit = int(delta.total_seconds() // 60)

            # 4. Simpan ke Database
            new_log = Presensi(
                user_pin=attendance_id,
                device_sn=device_klien_sn,
                waktu_scan=now,
                tipe_absen=status_absen,
                status_kehadiran=status_kehadiran,
                keterlambatan_menit=keterlambatan_menit
            )
            db.session.add(new_log)
            db.session.commit()

            late_info = f" | Terlambat: {keterlambatan_menit} menit" if status_kehadiran == "LATE" else ""
            sync_tag = " [OFFLINE-SYNC]" if is_offline_sync else ""
            print(f"\n🟢 [FACE-AI]{sync_tag} MATCH: {best_name} (NIP: {best_nip}) | Similarity: {similarity_pct}% | Status: {status_absen} | {status_kehadiran}{late_info}")
            print(f"   ↳ Waktu: {now.strftime('%H:%M:%S')} | Device: {device_klien_sn} | AttendanceID: {attendance_id}\n")
            
            return jsonify({
                "nip": best_nip,
                "name": best_name,
                "status": f"Presensi {status_absen} Berhasil",
                "status_kehadiran": status_kehadiran,
                "keterlambatan_menit": keterlambatan_menit,
                "waktu": now.strftime("%H:%M:%S"),
                "is_offline_sync": is_offline_sync
            }), 200

    # ── STRICT REJECTION: Wajah tidak dikenali atau di bawah threshold ──
    similarity_pct = float(round(best_similarity * 100, 1))
    print(f"\n🔴 [FACE-AI] UNKNOWN FACE! | Highest Similarity: {similarity_pct}% | Threshold: {round(THRESHOLD * 100, 1)}%")
    if best_name != "unknown":
        print(f"   ↳ Closest match: {best_name} (NIP: {best_nip}) — skor di bawah threshold\n")
    else:
        print(f"   ↳ Tidak ada embedding yang cocok di database\n")

    return jsonify({
        "error": "UNKNOWN_FACE",
        "message": "Wajah tidak dikenali atau di bawah ambang batas kemiripan. Silakan coba lagi.",
        "similarity": similarity_pct,
    }), 401

# ==========================================
# 3b. BIOMETRIC ADMIN UNLOCK (Face-based Kiosk Unlock)
# ==========================================
@api_blueprint.route('/predict/unlock', methods=['POST'])
def predict_unlock():
    """
    Biometric Admin Verification — Admin scan wajah untuk unlock menu kiosk.
    
    Flow:
      1. Admin scan wajah di kiosk
      2. Server identifikasi wajah (MTCNN + FaceNet)
      3. Cek apakah user adalah admin (super_admin atau admin_opd)
      4. Jika admin_opd, cek apakah OPD admin cocok dengan OPD device
      5. Return unlock=true jika semua validasi pass
    
    Request: multipart/form-data
      - photo: file foto wajah
      - device_sn: serial number device kiosk
    """
    if 'photo' not in request.files:
        return jsonify({"error": "Foto wajah wajib disertakan."}), 400

    device_sn = request.form.get('device_sn', '')
    if not device_sn:
        return jsonify({"error": "Device SN wajib disertakan."}), 400

    # --- Validasi Device (DeviceUnbound check) ---
    device = Device.query.get(device_sn)
    if not device or not device.verified or device.opd_id is None:
        return jsonify({
            "error": "DeviceUnbound",
            "message": "Perangkat telah diputus aksesnya oleh server. Silakan aktivasi ulang."
        }), 403

    # --- Face Recognition Pipeline ---
    photo = request.files['photo']
    if not allowed_file(photo.filename):
        return jsonify({"error": "Format file tidak valid."}), 400

    temp_filename = f"{uuid4().hex}.jpg"
    image_path = os.path.join(TEMP_DIR, temp_filename)
    photo.save(image_path)

    test_embedding, test_embedding_flip = get_embeddings(image_path)
    os.remove(image_path)

    if test_embedding is None:
        return jsonify({"error": "Wajah tidak terdeteksi. Pastikan wajah terlihat jelas."}), 400

    # --- Cari kecocokan di semua embedding ---
    best_nip, best_name, best_similarity = "unknown", "unknown", 0.0

    for folder_name in os.listdir(EMBEDDINGS_DIR):
        pkl_path = os.path.join(EMBEDDINGS_DIR, folder_name, f"{folder_name}.pkl")
        txt_path = os.path.join(EMBEDDINGS_DIR, folder_name, f"{folder_name}.txt")

        if not os.path.exists(pkl_path) or not os.path.exists(txt_path):
            continue

        with open(pkl_path, "rb") as f:
            known_embeddings = pickle.load(f)

        similarity = compare_faces(test_embedding, known_embeddings, THRESHOLD, test_embedding_flip)
        if similarity > best_similarity:
            best_similarity = similarity
            best_nip, best_name = read_txt(txt_path)

    similarity_pct = float(round(best_similarity * 100, 1))

    # --- Threshold Check ---
    if best_nip == "unknown" or best_similarity < THRESHOLD:
        print(f"\n🔒 [UNLOCK] GAGAL — Wajah tidak dikenali | Similarity: {similarity_pct}% | Device: {device_sn}")
        return jsonify({"unlock": False, "error": "Wajah tidak dikenali."}), 401

    # --- Role Validation ---
    user = User.query.filter_by(nip=best_nip).first()
    if not user:
        return jsonify({"unlock": False, "error": "User tidak ditemukan di database."}), 404

    if user.role == 'super_admin':
        print(f"\n🔓 [UNLOCK] OK — Super Admin: {user.nama_lengkap} | Similarity: {similarity_pct}% | Device: {device_sn}")
        return jsonify({
            "unlock": True,
            "role": "super_admin",
            "name": user.nama_lengkap,
            "nip": user.nip,
            "similarity": similarity_pct,
        }), 200

    if user.role == 'admin_opd':
        # Cek apakah OPD admin cocok dengan OPD device
        if device.opd_id and user.opd_id == device.opd_id:
            opd_name = user.opd.nama_opd if user.opd else "-"
            print(f"\n🔓 [UNLOCK] OK — Admin OPD: {user.nama_lengkap} ({opd_name}) | Similarity: {similarity_pct}% | Device: {device_sn}")
            return jsonify({
                "unlock": True,
                "role": "admin_opd",
                "name": user.nama_lengkap,
                "nip": user.nip,
                "opd_id": user.opd_id,
                "similarity": similarity_pct,
            }), 200
        else:
            device_opd = MasterOpd.query.get(device.opd_id) if device.opd_id else None
            device_opd_name = device_opd.nama_opd if device_opd else "Tidak terikat"
            print(f"\n🔒 [UNLOCK] DITOLAK — {user.nama_lengkap} bukan Admin untuk device ini | User OPD: {user.opd_id} | Device OPD: {device.opd_id} ({device_opd_name})")
            return jsonify({
                "unlock": False,
                "error": f"Anda bukan Admin instansi ini. Device terikat ke: {device_opd_name}.",
            }), 403

    # ASN atau role lain — tidak boleh unlock
    print(f"\n🔒 [UNLOCK] DITOLAK — {user.nama_lengkap} (role: {user.role}) bukan Admin | Device: {device_sn}")
    return jsonify({"unlock": False, "error": "Akses khusus Admin. ASN tidak dapat membuka menu ini."}), 403

# ==========================================
# 4. DASHBOARD & MANAGE ASN (PERBAIKAN user_pin)
# ==========================================
@api_blueprint.route('/report', methods=['GET'])
@token_required
def get_report(current_user):
    from models import DataPegawai, HariLiburCustom

    # --- Query Parameters ---
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    search_query = request.args.get('search_name', '', type=str).strip()
    status_filter = request.args.get('status_filter', '', type=str).strip().upper()
    kegiatan_id_filter = request.args.get('kegiatan_id', type=int)  # Optional: filter by kegiatan
    role_filter = request.args.get('role', '', type=str).lower()

    today = get_wib_time().date()
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else today
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else today
    except ValueError:
        return jsonify({"error": "Format tanggal tidak valid. Gunakan YYYY-MM-DD."}), 400

    if start_date > end_date:
        return jsonify({"error": "start_date tidak boleh lebih besar dari end_date."}), 400
    if (end_date - start_date).days > 93:
        return jsonify({"error": "Rentang tanggal maksimum 93 hari."}), 400

    # ────────────────────────────────────────────────────────
    # NOTE: kegiatan_id filter on DAILY report is no longer used
    # (kegiatan presensi now uses separate /api/report/kegiatan)
    # ────────────────────────────────────────────────────────
    enrolled_nips = None  # Not used for daily report anymore

    # ────────────────────────────────────────────────────────
    # STEP 1: Ambil SEMUA log presensi dalam rentang tanggal
    #         Scope admin_opd berdasarkan DEVICE OPD (bukan user OPD)
    # ────────────────────────────────────────────────────────
    presensi_q = Presensi.query.filter(
        db.func.date(Presensi.waktu_scan) >= start_date,
        db.func.date(Presensi.waktu_scan) <= end_date,
    )
    # Filter by kegiatan_id if provided
    if kegiatan_id_filter:
        presensi_q = presensi_q.filter(Presensi.kegiatan_id == kegiatan_id_filter)
        
    # Filter by role (ASN / Non-ASN)
    if role_filter:
        presensi_q = presensi_q.join(
            User,
            db.or_(Presensi.user_pin == User.nip, Presensi.user_pin == User.pin)
        ).filter(User.role == role_filter)
        
    if current_user.role == 'admin_opd':
        opd_device_sns = [d.sn for d in Device.query.filter_by(opd_id=current_user.opd_id).all()]
        if opd_device_sns:
            presensi_q = presensi_q.filter(Presensi.device_sn.in_(opd_device_sns))
        else:
            presensi_q = presensi_q.filter(False)

    all_logs = presensi_q.all()

    # ────────────────────────────────────────────────────────
    # STEP 2: Resolve identity via data_pegawai (LEFT JOIN fallback)
    #         data_pegawai is the source of truth for NIP & nama
    # ────────────────────────────────────────────────────────
    unique_ids = set(log.user_pin for log in all_logs if log.user_pin)
    pin_identity = {}
    for uid in unique_ids:
        # user_pin now stores NIP/NIK (from /predict's best_nip). Try nip first, then pin.
        user = User.query.filter_by(nip=uid).first() or User.query.filter_by(pin=uid).first()
        user_role = user.role if user else 'asn'
        pegawai = DataPegawai.query.filter_by(nip=uid).first() or DataPegawai.query.filter_by(pin=uid).first()
        if pegawai:
            pin_identity[uid] = {"nip": pegawai.nip, "nama": pegawai.nama_lengkap, "role": user_role}
        elif user:
            pin_identity[uid] = {"nip": user.nip or uid, "nama": user.nama_lengkap, "role": user_role}
        else:
            pin_identity[uid] = {"nip": uid, "nama": f"Unknown ({uid})", "role": "asn"}

    # ────────────────────────────────────────────────────────
    # STEP 3: Index logs by (pin, date) and group IN/OUT
    # ────────────────────────────────────────────────────────
    logs_index = {}
    for log in all_logs:
        key = (log.user_pin, log.waktu_scan.date())
        logs_index.setdefault(key, []).append(log)

    report_data = []
    for (pin, log_date), logs in logs_index.items():
        identity = pin_identity.get(pin, {"nip": pin, "nama": f"Unknown ({pin})"})

        in_logs = [l for l in logs if l.tipe_absen == 'IN']
        out_logs = [l for l in logs if l.tipe_absen == 'OUT']

        earliest_in = min(in_logs, key=lambda l: l.waktu_scan) if in_logs else None
        latest_out = max(out_logs, key=lambda l: l.waktu_scan) if out_logs else None

        active_sn = earliest_in.device_sn if earliest_in else (latest_out.device_sn if latest_out else None)
        lokasi = None
        if active_sn:
            mesin = SnMesin.query.get(active_sn)
            lokasi = mesin.nama_lokasi if mesin else None

        report_data.append({
            "nip": identity["nip"],
            "nama": identity["nama"],
            "role": identity.get("role", "asn"),
            "tanggal": log_date.strftime("%Y-%m-%d"),
            "jam_masuk": earliest_in.waktu_scan.strftime("%H:%M:%S") if earliest_in else None,
            "status_masuk": earliest_in.status_kehadiran if earliest_in else None,
            "keterlambatan_menit": (earliest_in.keterlambatan_menit or 0) if earliest_in else 0,
            "jam_keluar": latest_out.waktu_scan.strftime("%H:%M:%S") if latest_out else None,
            "status_keluar": "CHECKED_OUT" if latest_out else "MISSING",
            "device_sn": active_sn,
            "nama_lokasi": lokasi,
        })

    # SECURITY FIX: Enforce tenant isolation on presensi-derived rows
    # For admin_opd: restrict to employees who belong to THEIR OPD
    if current_user.role == 'admin_opd':
        opd_nips = set(
            u.nip for u in User.query.filter_by(opd_id=current_user.opd_id).all()
            if u.nip
        )
        report_data = [r for r in report_data if str(r['nip']) in opd_nips]

    # Then further restrict to enrolled NIPs if kegiatan_id is set
    if enrolled_nips is not None:
        enrolled_set = set(enrolled_nips)
        report_data = [r for r in report_data if str(r['nip']) in enrolled_set]

    # ────────────────────────────────────────────────────────
    # STEP 4: Generate virtual ABSENT rows for ALL users
    #         (Admin + ASN — anyone who should be present)
    # ────────────────────────────────────────────────────────
    known_users_q = User.query
    if current_user.role == 'admin_opd':
        known_users_q = known_users_q.filter_by(opd_id=current_user.opd_id)
    # ── Apply role filter to ABSENT generator too ──
    if role_filter:
        known_users_q = known_users_q.filter(User.role == role_filter)
    known_users = known_users_q.all()

    # SECURITY FIX: When kegiatan_id is set, intersect enrolled NIPs with OPD scope
    # Ensures: "employees in enrolled_nips AND whose opd_id equals Admin's opd_id"
    if enrolled_nips is not None:
        known_users = [u for u in known_users if (u.nip or '') in enrolled_nips]

    existing_keys = set(logs_index.keys())
    id_holidays_cache = {}

    # Pre-load custom holidays for the date range
    custom_holidays_in_range = HariLiburCustom.query.filter(
        HariLiburCustom.tanggal >= start_date,
        HariLiburCustom.tanggal <= end_date
    ).all()
    custom_holiday_dates = set(h.tanggal for h in custom_holidays_in_range)

    current_date = start_date
    while current_date <= end_date:
        yr = current_date.year
        if yr not in id_holidays_cache:
            id_holidays_cache[yr] = holidays.Indonesia(years=yr)

        is_holiday = (
            current_date.weekday() >= 5
            or current_date in id_holidays_cache[yr]
            or current_date in custom_holiday_dates
        )

        if not is_holiday and current_date <= today:
            for u in known_users:
                attendance_id = u.nip if u.nip else u.pin
                if not attendance_id:
                    continue
                if (attendance_id, current_date) not in existing_keys:
                    identity = pin_identity.get(attendance_id)
                    if not identity:
                        identity = {"nip": u.nip or attendance_id, "nama": u.nama_lengkap}
                    report_data.append({
                        "nip": identity["nip"],
                        "nama": identity["nama"],
                        "role": u.role,
                        "tanggal": current_date.strftime("%Y-%m-%d"),
                        "jam_masuk": None,
                        "status_masuk": "ABSENT",
                        "keterlambatan_menit": 0,
                        "jam_keluar": None,
                        "status_keluar": "MISSING",
                        "device_sn": None,
                        "nama_lokasi": None,
                    })
        current_date += timedelta(days=1)

    # ────────────────────────────────────────────────────────
    # STEP 5: Search filter (by nama or NIP)
    # ────────────────────────────────────────────────────────
    if search_query:
        sq = search_query.lower()
        report_data = [r for r in report_data if sq in r['nama'].lower() or sq in str(r['nip']).lower()]

    # ────────────────────────────────────────────────────────
    # STEP 6: Status filter
    # ────────────────────────────────────────────────────────
    if status_filter:
        valid_statuses = ['ON_TIME', 'LATE', 'ABSENT']
        if status_filter not in valid_statuses:
            return jsonify({"error": f"status_filter tidak valid. Gunakan: {', '.join(valid_statuses)}"}), 400
        report_data = [r for r in report_data if r['status_masuk'] == status_filter]

    # ────────────────────────────────────────────────────────
    # STEP 7: Sorting (tanggal desc, nama asc)
    # ────────────────────────────────────────────────────────
    report_data.sort(key=lambda x: x['nama'])
    report_data.sort(key=lambda x: x['tanggal'], reverse=True)

    # ────────────────────────────────────────────────────────
    # STEP 8: Pagination
    # ────────────────────────────────────────────────────────
    total_records = len(report_data)
    total_pages = math.ceil(total_records / limit) if total_records > 0 else 1
    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * limit
    end_idx = start_idx + limit
    paginated_data = report_data[start_idx:end_idx]

    return jsonify({
        "data": paginated_data,
        "total_pages": total_pages,
        "current_page": page,
        "total_records": total_records
    }), 200

@api_blueprint.route('/manage-asn', methods=['GET'])
@token_required
def get_manage_asn(current_user):
    today = datetime.now().date()
    role_filter = request.args.get('role', '', type=str).lower()

    # ── Fetch ALL users (ASN + Admin + Super Admin) ──
    # Admins are employees too — they need attendance monitoring.
    # Security is enforced via the `is_manageable` flag, not by hiding data.
    if current_user.role == 'super_admin':
        users = User.query.all()
    else:
        # admin_opd: Users in my OPD + users with cross-OPD access to my OPD
        primary_users = User.query.filter_by(opd_id=current_user.opd_id).all()

        cross_nips = [a.user_nip for a in UserAksesOpd.query.filter_by(
            opd_id=current_user.opd_id, approval_status='approved'
        ).all()]
        cross_users = User.query.filter(
            User.nip.in_(cross_nips)
        ).all() if cross_nips else []

        seen_ids = set()
        users = []
        for u in primary_users + cross_users:
            if u.id not in seen_ids:
                seen_ids.add(u.id)
                users.append(u)

    if role_filter:
        users = [u for u in users if u.role == role_filter]

    data_asn = []
    for user in users:
        # ── Attendance identifier: NIP is always set by registration (ASN=18digit, Non-ASN=16digit NIK) ──
        attendance_id = user.nip if user.nip else user.pin

        # ── Status Kehadiran Hari Ini ──
        logs_today = Presensi.query.filter(
            Presensi.user_pin == attendance_id,
            db.func.date(Presensi.waktu_scan) == today
        ).all()

        status_hari_ini = "Belum Hadir"
        if logs_today:
            has_out = any(log.tipe_absen == 'OUT' for log in logs_today)
            has_in = any(log.tipe_absen == 'IN' for log in logs_today)
            if has_out:
                status_hari_ini = "Sudah Keluar"
            elif has_in:
                status_hari_ini = "Hadir"

        # ── Cross-OPD Privileges ──
        cross_opd_list = []
        if user.nip:
            akses_records = UserAksesOpd.query.filter_by(user_nip=user.nip).all()
            for akses in akses_records:
                opd_target = MasterOpd.query.get(akses.opd_id)
                cross_opd_list.append({
                    "akses_id": akses.id,
                    "opd_id": akses.opd_id,
                    "opd_nama": opd_target.nama_opd if opd_target else "-",
                    "approval_status": akses.approval_status or "approved",
                })

        # ── Permission Flag: can the logged-in user manage this row? ──
        # super_admin can manage everyone.
        # admin_opd can only manage ASN accounts, not other admins.
        if current_user.role == 'super_admin':
            is_manageable = True
        else:
            is_manageable = (user.role == 'asn')

        data_asn.append({
            "id": user.id,
            "nip": user.nip,
            "nama": user.nama_lengkap,
            "role": user.role,
            "opd": user.opd.nama_opd if user.opd else "-",
            "opd_id": user.opd_id,
            "status_hari_ini": status_hari_ini,
            "is_face_registered": user.is_face_registered,
            "is_manageable": is_manageable,
            "cross_opd_privileges": cross_opd_list,
        })

    return jsonify(data_asn), 200


@api_blueprint.route('/users/akses-opd/<int:akses_id>', methods=['DELETE'])
@token_required
def revoke_cross_opd(current_user, akses_id):
    """Revoke a cross-OPD access privilege by its ID."""
    if current_user.role not in ['admin_opd', 'super_admin']:
        return jsonify({"error": "Akses ditolak."}), 403

    akses = UserAksesOpd.query.get(akses_id)
    if not akses:
        return jsonify({"error": "Record akses OPD tidak ditemukan."}), 404

    # admin_opd hanya bisa revoke akses untuk OPD miliknya
    if current_user.role == 'admin_opd' and akses.opd_id != current_user.opd_id:
        return jsonify({"error": "Anda tidak berhak mencabut akses OPD ini."}), 403

    opd_target = MasterOpd.query.get(akses.opd_id)
    opd_nama = opd_target.nama_opd if opd_target else akses.opd_id
    user_nip = akses.user_nip

    db.session.delete(akses)
    catat_audit(
        current_user.id, "REVOKE_CROSS_OPD", "user_akses_opd",
        f"Mencabut akses OPD '{opd_nama}' dari NIP {user_nip}",
        target_record_id=str(akses_id)
    )

    return jsonify({"message": f"Akses OPD '{opd_nama}' untuk NIP {user_nip} berhasil dicabut."}), 200

# ==========================================
# 4b. SYSTEM SETTINGS & CUSTOM HOLIDAYS (Super Admin)
# ==========================================
@api_blueprint.route('/settings', methods=['GET'])
@token_required
def get_settings(current_user):
    if current_user.role != 'super_admin':
        return jsonify({"error": "Hanya Super Admin yang dapat mengakses pengaturan."}), 403

    defaults = {
        'JAM_MASUK_MULAI': ('06:00:00', 'Kiosk mulai menerima scan masuk'),
        'BATAS_TERLAMBAT': ('08:00:00', 'Lewat jam ini dianggap TERLAMBAT'),
        'JAM_MASUK_AKHIR': ('12:00:00', 'Kiosk berhenti menerima scan masuk'),
        'JAM_KELUAR_MULAI': ('15:00:00', 'Kiosk mulai menerima scan pulang'),
        'JAM_KELUAR_AKHIR': ('20:00:00', 'Kiosk berhenti menerima scan pulang'),
    }

    # Auto-seed missing default keys
    for k, (val, desc) in defaults.items():
        if not AppSetting.query.get(k):
            db.session.add(AppSetting(setting_key=k, setting_value=val, description=desc))
    db.session.commit()

    rows = AppSetting.query.all()
    return jsonify([{
        "key": r.setting_key,
        "value": r.setting_value,
        "description": r.description,
        "updated_at": r.updated_at.strftime("%Y-%m-%d %H:%M:%S") if r.updated_at else None
    } for r in rows]), 200

@api_blueprint.route('/settings', methods=['PUT'])
@token_required
def update_settings(current_user):
    if current_user.role != 'super_admin':
        return jsonify({"error": "Hanya Super Admin yang dapat mengubah pengaturan."}), 403
    data = request.get_json()
    if not data or not isinstance(data, dict):
        return jsonify({"error": "Body harus berupa JSON object {key: value, ...}"}), 400

    updated = []
    for key, value in data.items():
        row = AppSetting.query.get(key)
        if row:
            row.setting_value = str(value)
        else:
            row = AppSetting(setting_key=key, setting_value=str(value))
            db.session.add(row)
        updated.append(key)
    db.session.commit()
    return jsonify({"message": f"{len(updated)} pengaturan berhasil diperbarui.", "updated_keys": updated}), 200

@api_blueprint.route('/holidays', methods=['GET'])
@token_required
def get_holidays(current_user):
    if current_user.role != 'super_admin':
        return jsonify({"error": "Akses ditolak."}), 403
    rows = HariLiburCustom.query.order_by(HariLiburCustom.tanggal.desc()).all()
    return jsonify([{
        "id": r.id, "tanggal": r.tanggal.strftime("%Y-%m-%d"),
        "keterangan": r.keterangan,
        "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None
    } for r in rows]), 200

@api_blueprint.route('/holidays', methods=['POST'])
@token_required
def add_holiday(current_user):
    if current_user.role != 'super_admin':
        return jsonify({"error": "Akses ditolak."}), 403
    data = request.get_json()
    tanggal_str = data.get('tanggal')
    keterangan = data.get('keterangan', '').strip()
    if not tanggal_str or not keterangan:
        return jsonify({"error": "Field 'tanggal' dan 'keterangan' wajib diisi."}), 400
    try:
        tgl = datetime.strptime(tanggal_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({"error": "Format tanggal tidak valid. Gunakan YYYY-MM-DD."}), 400

    existing = HariLiburCustom.query.filter_by(tanggal=tgl).first()
    if existing:
        return jsonify({"error": f"Tanggal {tanggal_str} sudah terdaftar sebagai hari libur."}), 409

    new_holiday = HariLiburCustom(tanggal=tgl, keterangan=keterangan)
    db.session.add(new_holiday)
    db.session.commit()
    return jsonify({"message": f"Hari libur '{keterangan}' pada {tanggal_str} berhasil ditambahkan.", "id": new_holiday.id}), 201

@api_blueprint.route('/holidays/<int:holiday_id>', methods=['DELETE'])
@token_required
def delete_holiday(current_user, holiday_id):
    if current_user.role != 'super_admin':
        return jsonify({"error": "Akses ditolak."}), 403
    h = HariLiburCustom.query.get(holiday_id)
    if not h:
        return jsonify({"error": "Data hari libur tidak ditemukan."}), 404
    keterangan = h.keterangan
    db.session.delete(h)
    db.session.commit()
    return jsonify({"message": f"Hari libur '{keterangan}' berhasil dihapus."}), 200

@api_blueprint.route('/users/<int:id>', methods=['DELETE'])
@token_required
def delete_user(current_user, id):
    if current_user.role not in ['admin_opd', 'super_admin']:
        return jsonify({"message": "Akses ditolak!"}), 403

    user_to_delete = User.query.get(id)
    if not user_to_delete: return jsonify({"message": "User tidak ditemukan!"}), 404
    if current_user.role == 'admin_opd' and current_user.opd_id != user_to_delete.opd_id:
        return jsonify({"message": "Akses ditolak! ASN ini bukan dari instansi Anda."}), 403

    nama_asn = user_to_delete.nama_lengkap
    db.session.delete(user_to_delete)
    # PERBAIKAN: Gunakan current_user.id
    catat_audit(current_user.id, "DELETE_USER", "users", f"Menghapus ASN {nama_asn} (NIP: {user_to_delete.nip})")
    
    return jsonify({"message": f"ASN {nama_asn} berhasil dihapus!"}), 200

# ==========================================
# 5. REGISTER Wajah (Cross-OPD + Mobile Support)
# ==========================================

def _process_registration(person_nip, person_name, files, target_opd_id, source, actor_id=None, role='ASN'):
    """
    Logika inti registrasi wajah. Dipanggil oleh register_web (JWT) dan register_mobile (Device SN).
    
    Mendukung 2 mode:
      - ASN: Validasi NIP (18 digit) terhadap data_pegawai. Support cross-OPD.
      - NON_ASN: Bypass validasi master. NIK (16 digit) disimpan di kolom nip. Tanpa cross-OPD.
    
    3 Kondisi (ASN):
      A) User Baru → Buat user + embedding + akses OPD
      B) User Ada, OPD Sama → Tolak (sudah terdaftar)
      C) User Ada, OPD Beda → Tambah akses lintas instansi (TANPA duplikat user/embedding)
    """
    initial_approval = 'approved' if source in ('web', 'kiosk') else 'pending'
    is_non_asn = (role.upper() == 'NON_ASN')

    # --- Validasi Target OPD ---
    target_opd = MasterOpd.query.get(target_opd_id)
    if not target_opd:
        return jsonify({"error": "Gagal: Instansi (OPD) tujuan tidak ditemukan."}), 404

    # =============================================
    # NON-ASN MODE: Bypass data_pegawai validation
    # =============================================
    if is_non_asn:
        # Cek duplikat: apakah NIK sudah terdaftar?
        existing_user = User.query.filter_by(nip=person_nip).first()
        if existing_user:
            return jsonify({"error": "Gagal: NIK ini sudah terdaftar di sistem."}), 400

        # Generate face embeddings
        result, status = register_user_and_generate_embeddings(person_nip, person_name, files)
        if status != 200:
            return jsonify(result), status

        new_user = User(
            nip=person_nip,
            pin=None,  # Non-ASN tidak punya PIN dari data_pegawai
            nama_lengkap=person_name,
            role='non_asn',
            opd_id=target_opd_id,
            is_face_registered=True,
            approval_status=initial_approval
        )
        db.session.add(new_user)

        if actor_id:
            catat_audit(
                actor_id, "REGISTER_NON_ASN", "users",
                f"Mendaftarkan Non-ASN: {person_name} (NIK: {person_nip}) untuk OPD {target_opd.nama_opd} (source: {source})"
            )
        db.session.commit()

        print(f"   ✅ [NON-ASN] {person_name} (NIK: {person_nip}) → {target_opd.nama_opd}")
        return jsonify({
            "message": f"Registrasi Non-ASN berhasil! {person_name} terdaftar di {target_opd.nama_opd}.",
            "nip": person_nip,
            "role": "non_asn",
            "primary_opd": target_opd.nama_opd,
            "approval_status": initial_approval
        }), 200

    # =============================================
    # ASN MODE: Strict validation against data_pegawai
    # =============================================
    pegawai = DataPegawai.query.filter_by(nip=person_nip).first()
    if not pegawai:
        return jsonify({"error": "Gagal: NIP tidak ditemukan di Data Induk Pegawai. Sinkronkan data dari SPOT terlebih dahulu."}), 400

    # --- Cek apakah user sudah ada ---
    existing_user = User.query.filter_by(nip=person_nip).first()

    # =============================================
    # CONDITION A: User Baru (Belum ada di tabel users)
    # =============================================
    if not existing_user:
        result, status = register_user_and_generate_embeddings(person_nip, person_name, files)
        if status != 200:
            return jsonify(result), status

        new_user = User(
            nip=person_nip,
            pin=pegawai.pin,
            nama_lengkap=person_name,
            role='asn',
            opd_id=target_opd_id,
            is_face_registered=True,
            approval_status=initial_approval
        )
        db.session.add(new_user)

        akses_baru = UserAksesOpd(
            user_nip=person_nip,
            opd_id=target_opd_id,
            approval_status=initial_approval
        )
        db.session.add(akses_baru)

        if actor_id:
            catat_audit(
                actor_id, "REGISTER_ASN", "users",
                f"Mendaftarkan wajah ASN baru: {person_name} untuk OPD {target_opd.nama_opd} (source: {source})"
            )
        db.session.commit()

        msg = f"Registrasi berhasil! {person_name} terdaftar di {target_opd.nama_opd}."
        if initial_approval == 'pending':
            msg += " Akun menunggu persetujuan Admin sebelum bisa digunakan untuk presensi."

        return jsonify({
            "message": msg,
            "nip": person_nip,
            "role": "asn",
            "primary_opd": target_opd.nama_opd,
            "approval_status": initial_approval
        }), 200

    # =============================================
    # CONDITION B: User Sudah Ada, OPD Sama → Tolak
    # =============================================
    if existing_user.opd_id == target_opd_id:
        return jsonify({
            "error": "Gagal: ASN dengan NIP ini sudah terdaftar di instansi ini."
        }), 400

    # Cek juga di tabel akses lintas instansi
    existing_akses = UserAksesOpd.query.filter_by(
        user_nip=person_nip,
        opd_id=target_opd_id
    ).first()

    if existing_akses:
        return jsonify({
            "error": "Gagal: Akses lintas instansi sudah terdaftar di OPD ini."
        }), 400

    # =============================================
    # CONDITION C: User Ada, OPD Beda → Cross-OPD Access
    # (TIDAK membuat user baru, TIDAK re-generate embedding)
    # =============================================
    akses_lintas = UserAksesOpd(
        user_nip=person_nip,
        opd_id=target_opd_id,
        approval_status=initial_approval
    )
    db.session.add(akses_lintas)

    primary_opd = MasterOpd.query.get(existing_user.opd_id)
    primary_opd_name = primary_opd.nama_opd if primary_opd else "-"

    if actor_id:
        catat_audit(
            actor_id, "CROSS_OPD_REGISTER", "user_akses_opd",
            f"ASN {person_name} menambahkan akses lintas instansi ke {target_opd.nama_opd} (source: {source})"
        )
    db.session.commit()

    msg = f"Akses lintas instansi berhasil ditambahkan ke {target_opd.nama_opd}. Instansi utama tetap {primary_opd_name}."
    if initial_approval == 'pending':
        msg += " Akses menunggu persetujuan Admin."

    return jsonify({
        "message": msg,
        "nip": person_nip,
        "primary_opd": primary_opd_name,
        "new_access_opd": target_opd.nama_opd,
        "approval_status": initial_approval
    }), 200


# --- Route A: Registrasi dari Web Dashboard (JWT Required) ---
@api_blueprint.route('/register', methods=['POST'])
@token_required
def register_web(current_user):
    if 'nip' not in request.form or 'name' not in request.form:
        return jsonify({"error": "NIP/NIK dan Nama wajib diisi"}), 400

    person_nip = request.form['nip']
    person_name = request.form['name']
    role = request.form.get('role', 'ASN').upper()
    files = request.files.getlist('photos')
    target_opd_id = request.form.get('opd_id', type=int) or current_user.opd_id

    # Digit length validation based on role
    if role == 'NON_ASN':
        if len(person_nip) != 16 or not person_nip.isdigit():
            return jsonify({"error": "NIK harus 16 digit angka."}), 400
    else:
        if len(person_nip) != 18 or not person_nip.isdigit():
            return jsonify({"error": "NIP harus 18 digit angka."}), 400

    if len(files) < 5:
        return jsonify({"error": "Minimal 5 foto wajah diperlukan."}), 400
    for file in files:
        if not allowed_file(file.filename) or not is_valid_image(file):
            return jsonify({"error": "File tidak valid. Gunakan format PNG/JPG/JPEG."}), 400

    return _process_registration(person_nip, person_name, files, target_opd_id, 'web', actor_id=current_user.id, role=role)


# --- Route B: Registrasi dari Mobile Kiosk (Device SN Auth, Tanpa JWT) ---
@api_blueprint.route('/register/mobile', methods=['POST'])
def register_mobile():
    """
    Endpoint khusus registrasi dari Flutter Kiosk.
    
    Keamanan:
      - Validasi device_sn yang sudah terdaftar, verified, dan terikat ke OPD.
      - OPD otomatis diambil dari device.opd_id (hasil binding oleh Admin).
      - Tidak perlu opd_id dari client → mencegah manipulasi.
      - Status langsung 'approved' karena Admin sudah unlock kiosk.
    """
    # --- Security: Validasi Device SN ---
    device_sn = request.form.get('device_sn', '')
    if not device_sn:
        return jsonify({"error": "Device SN wajib disertakan."}), 400

    device = Device.query.get(device_sn)
    if not device:
        return jsonify({"error": f"Perangkat '{device_sn}' tidak terdaftar di sistem."}), 403
    if not device.verified:
        return jsonify({"error": f"Perangkat '{device_sn}' belum diverifikasi oleh Admin."}), 403
    if not device.opd_id:
        return jsonify({"error": f"Perangkat '{device_sn}' belum terikat ke instansi manapun. Minta Admin untuk melakukan binding terlebih dahulu."}), 403

    # OPD diambil dari device binding, BUKAN dari client
    target_opd_id = device.opd_id

    # --- Validasi Input ---
    if 'nip' not in request.form or 'name' not in request.form:
        return jsonify({"error": "NIP/NIK dan Nama wajib diisi."}), 400

    person_nip = request.form['nip']
    person_name = request.form['name']
    role = request.form.get('role', 'ASN').upper()
    files = request.files.getlist('photos')

    # Digit length validation based on role
    if role == 'NON_ASN':
        if len(person_nip) != 16 or not person_nip.isdigit():
            return jsonify({"error": "NIK harus 16 digit angka."}), 400
    else:
        if len(person_nip) != 18 or not person_nip.isdigit():
            return jsonify({"error": "NIP harus 18 digit angka."}), 400

    if len(files) < 5:
        return jsonify({"error": "Minimal 5 foto wajah diperlukan."}), 400
    for file in files:
        if not allowed_file(file.filename) or not is_valid_image(file):
            return jsonify({"error": "File tidak valid. Gunakan format PNG/JPG/JPEG."}), 400

    return _process_registration(person_nip, person_name, files, target_opd_id, 'kiosk', role=role)

# ==========================================
# 5b. UPDATE PROFIL ASN + RE-REGISTRASI WAJAH
# ==========================================
@api_blueprint.route('/users/update/<string:nip>', methods=['PUT'])
@token_required
def update_user_profile(current_user, nip):
    """Update data ASN (nama, opd) dan opsional re-register wajah dengan foto baru."""
    if current_user.role not in ('super_admin', 'admin_opd'):
        return jsonify({"message": "Akses Ditolak!"}), 403

    user = User.query.filter_by(nip=nip).first()
    if not user:
        return jsonify({"error": f"ASN dengan NIP '{nip}' tidak ditemukan."}), 404

    # Scope check: Admin OPD hanya boleh edit ASN dari OPD-nya sendiri
    if current_user.role == 'admin_opd' and user.opd_id != current_user.opd_id:
        return jsonify({"error": "Anda hanya dapat mengedit ASN dari instansi Anda."}), 403

    changes = []

    # --- Update Nama ---
    new_name = request.form.get('name')
    if new_name and new_name != user.nama_lengkap:
        old_name = user.nama_lengkap
        user.nama_lengkap = new_name
        changes.append(f"Nama: '{old_name}' → '{new_name}'")

        # Update juga di DataPegawai agar konsisten
        pegawai = DataPegawai.query.filter_by(nip=nip).first()
        if pegawai:
            pegawai.nama_lengkap = new_name

    # --- Update OPD ---
    new_opd_id = request.form.get('opd_id', type=int)
    if new_opd_id and new_opd_id != user.opd_id:
        new_opd = MasterOpd.query.get(new_opd_id)
        if not new_opd:
            return jsonify({"error": "OPD tujuan tidak ditemukan."}), 404
        old_opd = user.opd.nama_opd if user.opd else '-'
        user.opd_id = new_opd_id
        changes.append(f"OPD: '{old_opd}' → '{new_opd.nama_opd}'")

        # Update UserAksesOpd juga
        akses = UserAksesOpd.query.filter_by(user_nip=nip, opd_id=user.opd_id).first()
        if akses:
            akses.opd_id = new_opd_id

    # --- Re-Register Wajah (Opsional) ---
    files = request.files.getlist('photos')
    if files and len(files) >= 5:
        # Validasi semua foto
        for file in files:
            if not allowed_file(file.filename) or not is_valid_image(file):
                return jsonify({"error": "File foto tidak valid. Gunakan format PNG/JPG/JPEG."}), 400

        # Hapus embedding lama
        curr_dir = os.getcwd()
        old_embedding_dir = os.path.join(curr_dir, "samples_embedding", nip)
        old_samples_dir = os.path.join(curr_dir, "samples", nip)

        if os.path.exists(old_embedding_dir):
            shutil.rmtree(old_embedding_dir)
            print(f"   🗑️ Embedding lama untuk {nip} dihapus.")
        if os.path.exists(old_samples_dir):
            shutil.rmtree(old_samples_dir)
            print(f"   🗑️ Sample foto lama untuk {nip} dihapus.")

        # Generate embedding baru
        display_name = new_name or user.nama_lengkap
        result, status = register_user_and_generate_embeddings(nip, display_name, files)
        if status != 200:
            return jsonify(result), status

        user.is_face_registered = True
        changes.append(f"Wajah di-registrasi ulang ({len(files)} foto baru)")

        # Catat audit khusus re-register
        catat_audit(
            current_user.id, "RE_REGISTER_FACE", "users",
            f"Re-registrasi wajah ASN {user.nama_lengkap} (NIP: {nip}) dengan {len(files)} foto baru",
            target_record_id=nip
        )
    elif files and len(files) < 5:
        return jsonify({"error": "Minimal 5 foto wajah diperlukan untuk re-registrasi."}), 400

    # --- Commit & Audit ---
    if changes:
        catat_audit(
            current_user.id, "UPDATE_ASN", "users",
            f"Update profil ASN {user.nama_lengkap}: {'; '.join(changes)}",
            target_record_id=nip
        )
        db.session.commit()
        return jsonify({"message": f"Profil {user.nama_lengkap} berhasil diperbarui.", "changes": changes}), 200
    else:
        return jsonify({"message": "Tidak ada perubahan yang dilakukan."}), 200

# ==========================================
# 5c. APPROVAL WORKFLOW (Pending → Approved/Rejected)
# ==========================================
@api_blueprint.route('/users/approve/<string:nip>', methods=['PUT'])
@token_required
def approve_user(current_user, nip):
    """Admin menyetujui atau menolak registrasi ASN (primary atau cross-OPD)."""
    if current_user.role not in ('super_admin', 'admin_opd'):
        return jsonify({"message": "Akses Ditolak!"}), 403

    data = request.get_json()
    new_status = data.get('status', 'approved').lower()
    target_opd_id = data.get('opd_id')  # Opsional: untuk cross-OPD approval

    if new_status not in ('approved', 'rejected'):
        return jsonify({"error": "Status harus 'approved' atau 'rejected'."}), 400

    user = User.query.filter_by(nip=nip).first()
    if not user:
        return jsonify({"error": f"ASN dengan NIP '{nip}' tidak ditemukan."}), 404

    # --- Cek apakah ini Cross-OPD approval ---
    if target_opd_id and int(target_opd_id) != user.opd_id:
        akses = UserAksesOpd.query.filter_by(user_nip=nip, opd_id=int(target_opd_id)).first()
        if not akses:
            return jsonify({"error": "Akses lintas instansi tidak ditemukan."}), 404
        
        # Scope check
        if current_user.role == 'admin_opd' and int(target_opd_id) != current_user.opd_id:
            return jsonify({"error": "Anda hanya dapat mengubah status akses dari instansi Anda."}), 403

        old_status = akses.approval_status
        akses.approval_status = new_status

        action_label = "APPROVE_CROSS_OPD" if new_status == 'approved' else "REJECT_CROSS_OPD"
        opd_target = MasterOpd.query.get(int(target_opd_id))
        catat_audit(
            current_user.id, action_label, "user_akses_opd",
            f"Akses lintas instansi {user.nama_lengkap} ke {opd_target.nama_opd if opd_target else 'OPD ' + str(target_opd_id)}: '{old_status}' -> '{new_status}'",
            target_record_id=nip
        )
        db.session.commit()

        status_label = "disetujui" if new_status == 'approved' else "ditolak"
        return jsonify({
            "message": f"Akses lintas instansi {user.nama_lengkap} telah {status_label}.",
            "nip": nip,
            "approval_status": new_status
        }), 200

    # --- Primary user approval ---
    if current_user.role == 'admin_opd' and user.opd_id != current_user.opd_id:
        return jsonify({"error": "Anda hanya dapat mengubah status ASN dari instansi Anda."}), 403

    old_status = user.approval_status
    user.approval_status = new_status

    # --- PENTING: Sinkronkan juga status di tabel user_akses_opd ---
    # Saat registrasi mobile, record dibuat di KEDUA tabel (users + user_akses_opd)
    # Jadi approval harus update KEDUA tabel agar konsisten
    akses_primary = UserAksesOpd.query.filter_by(user_nip=nip, opd_id=user.opd_id).first()
    if akses_primary:
        akses_primary.approval_status = new_status

    action_label = "APPROVE_ASN" if new_status == 'approved' else "REJECT_ASN"
    catat_audit(
        current_user.id, action_label, "users",
        f"Status ASN {user.nama_lengkap} (NIP: {nip}): '{old_status}' -> '{new_status}'",
        target_record_id=nip
    )
    db.session.commit()

    status_emoji = "✅" if new_status == 'approved' else "❌"
    print(f"\n{status_emoji} [APPROVAL] {user.nama_lengkap} (NIP: {nip}): '{old_status}' -> '{new_status}' | By: {current_user.nama_lengkap}")

    status_label = "disetujui" if new_status == 'approved' else "ditolak"
    return jsonify({
        "message": f"Registrasi {user.nama_lengkap} telah {status_label}.",
        "nip": nip,
        "approval_status": new_status
    }), 200

# ==========================================
# 5d. GET PENDING REGISTRATIONS
# ==========================================
@api_blueprint.route('/users/pending', methods=['GET'])
@token_required
def get_pending_users(current_user):
    """Menampilkan daftar ASN yang menunggu persetujuan."""
    if current_user.role not in ('super_admin', 'admin_opd'):
        return jsonify({"message": "Akses Ditolak!"}), 403

    query = User.query.filter_by(role='asn', approval_status='pending')

    # Admin OPD hanya bisa lihat pending dari OPD-nya sendiri
    if current_user.role == 'admin_opd':
        query = query.filter_by(opd_id=current_user.opd_id)

    pending_users = query.order_by(User.created_at.desc()).all()
    data = [{
        "nip": u.nip,
        "nama": u.nama_lengkap,
        "opd": u.opd.nama_opd if u.opd else "-",
        "is_face_registered": u.is_face_registered,
        "created_at": u.created_at.strftime("%Y-%m-%d %H:%M:%S") if u.created_at else None
    } for u in pending_users]

    return jsonify(data), 200

# ==========================================
# 6. PUBLIC OPD LIST (Untuk Flutter Kiosk tanpa Auth)
# ==========================================
@api_blueprint.route('/opd/list', methods=['GET'])
def public_opd_list():
    """Daftar OPD publik untuk dropdown registrasi di Kiosk App (tanpa JWT)."""
    opds = MasterOpd.query.all()
    return jsonify([{"id": o.id, "nama": o.nama_opd, "kode": o.kode_opd} for o in opds]), 200

# ==========================================
# 6b. MASTER DATA SYSTEM (SUPER ADMIN)
# ==========================================
@api_blueprint.route('/opd', methods=['GET', 'POST'])
@token_required
def manage_opd(current_user):
    if request.method == 'GET':
        scope = request.args.get('scope', '').lower()

        # scope=global: return ALL OPDs (safe fields only) for invitation dropdowns
        if scope == 'global':
            opds = MasterOpd.query.order_by(MasterOpd.nama_opd).all()
            return jsonify([{
                "id": o.id,
                "nama_opd": o.nama_opd,
                "kode_opd": o.kode_opd
            } for o in opds]), 200

        # Default: existing RBAC filter
        if current_user.role == 'super_admin':
            opds = MasterOpd.query.all()
        else:
            opds = MasterOpd.query.filter_by(id=current_user.opd_id).all()
        return jsonify([{"id": o.id, "nama": o.nama_opd, "kode": o.kode_opd} for o in opds]), 200
        
    if request.method == 'POST':
        if current_user.role != 'super_admin': return jsonify({"message": "Akses Ditolak"}), 403
        data = request.get_json()
        try:
            new_opd = MasterOpd(nama_opd=data['nama_opd'], kode_opd=data['kode_opd'])
            db.session.add(new_opd)
            db.session.flush()  # Flush agar PostgreSQL SERIAL id terisi sebelum audit
            
            catat_audit(current_user.id, "ADD_OPD", "master_opd", 
                        f"Menambah OPD: {data['nama_opd']}",
                        target_record_id=str(new_opd.id), auto_commit=False)
            db.session.commit()
            return jsonify({"message": "OPD berhasil ditambahkan!", "id": new_opd.id}), 201
        except Exception as e:
            db.session.rollback()
            print(f"[ADD_OPD] Error: {e}")
            return jsonify({"error": f"Gagal menambahkan OPD: {str(e)}"}), 500

@api_blueprint.route('/admin/add', methods=['POST'])
@token_required
def add_admin(current_user):
    if current_user.role != 'super_admin': 
        return jsonify({"message": "Akses Ditolak!"}), 403
        
    data = request.get_json()
    
    # Validasi input wajib
    nip = data.get('nip', '').strip()
    username = data.get('username', '').strip()
    nama = data.get('nama_lengkap', data.get('nama', '')).strip()
    password = data.get('password', '')
    opd_id = data.get('opd_id')

    if not nip or not username or not nama or not password:
        return jsonify({"message": "NIP, Username, Nama Lengkap, dan Password wajib diisi!"}), 400

    # 1. Cek apakah username sudah dipakai oleh user LAIN
    existing_username = User.query.filter_by(username=username).first()
    if existing_username:
        return jsonify({"message": f"Username '{username}' sudah digunakan!"}), 400

    from models import DataPegawai

    # 2. Cek apakah user dengan NIP ini sudah ada di tabel users (mungkin ASN yang di-elevate)
    existing_user = User.query.filter_by(nip=nip).first()

    if existing_user:
        # ASN yang sudah ada → elevate ke admin_opd
        if existing_user.role in ['admin_opd', 'super_admin']:
            return jsonify({"message": f"User dengan NIP '{nip}' sudah menjadi {existing_user.role}!"}), 400

        existing_user.username = username
        existing_user.nama_lengkap = nama
        existing_user.password_hash = generate_password_hash(password)
        existing_user.role = 'admin_opd'
        existing_user.opd_id = opd_id

        catat_audit(current_user.id, "ELEVATE_TO_ADMIN", "users",
                    f"Elevasi ASN '{nama}' (NIP: {nip}) menjadi Admin OPD",
                    target_record_id=str(existing_user.id))
        db.session.commit()

        print(f"\n👑 [ADMIN] ASN '{nama}' di-elevate ke Admin OPD | NIP: {nip} | Username: {username}")
        return jsonify({"message": f"ASN '{nama}' berhasil diangkat menjadi Admin OPD!"}), 200

    # 3. User belum ada → buat baru
    # Pastikan data_pegawai ada (karena FK constraint)
    pegawai = DataPegawai.query.filter_by(nip=nip).first()
    if not pegawai:
        new_pin = f"ADM-{uuid.uuid4().hex[:6].upper()}"
        pegawai = DataPegawai(
            pin=new_pin,
            nip=nip,
            nama_lengkap=nama
        )
        db.session.add(pegawai)
        db.session.flush()  # Agar FK constraint terpenuhi

    # 4. Buat akun Admin OPD baru
    new_admin = User(
        nip=pegawai.nip,
        pin=pegawai.pin,
        nama_lengkap=nama,
        username=username,
        password_hash=generate_password_hash(password),
        role='admin_opd',
        opd_id=opd_id,
        is_face_registered=False,
    )
    db.session.add(new_admin)
    
    catat_audit(current_user.id, "ADD_ADMIN", "users",
                f"Membuat akun Admin OPD baru: {nama} (NIP: {nip}, Username: {username})",
                target_record_id=nip)
    db.session.commit()

    print(f"\n✅ [ADMIN] Admin OPD baru: {nama} | NIP: {nip} | Username: {username}")
    return jsonify({"message": f"Admin '{nama}' berhasil ditambahkan!"}), 201

@api_blueprint.route('/admins', methods=['GET'])
@token_required
def get_admins(current_user):
    if current_user.role != 'super_admin': return jsonify({"message": "Akses Ditolak"}), 403

    # Query semua user dengan role admin_opd atau super_admin
    admins = User.query.filter(User.role.in_(['admin_opd', 'super_admin'])).all()
    data = []
    for a in admins:
        # Query SEMUA binding di tabel user_admin (1 admin bisa bind N device)
        bindings = UserAdmin.query.filter_by(user_id=a.id).all()
        bound_devices = [b.bound_device_sn for b in bindings if b.bound_device_sn]
        data.append({
            "id": a.id,
            "nip": a.nip,
            "username": a.username,
            "nama": a.nama_lengkap,
            "role": a.role,
            "opd": a.opd.nama_opd if a.opd else "-",
            "opd_id": a.opd_id,
            "is_face_registered": a.is_face_registered,
            "bound_devices": bound_devices,
        })
    return jsonify(data), 200

@api_blueprint.route('/devices', methods=['GET', 'POST'])
@token_required
def manage_devices(current_user):
    if current_user.role != 'super_admin': return jsonify({"message": "Akses Ditolak"}), 403
    if request.method == 'GET':
        # JOIN devices + sn_mesin untuk data lengkap
        devices = Device.query.all()
        data = []
        for d in devices:
            opd_name = "-"
            lokasi = "-"
            opd_id = None
            if d.pemetaan:
                opd_name = d.pemetaan.opd.nama_opd if d.pemetaan.opd else "-"
                lokasi = d.pemetaan.nama_lokasi or "-"
                opd_id = d.pemetaan.opd_id
            data.append({
                "sn": d.sn,
                "name": d.name,
                "device_name": d.device_name,
                "mac_address": d.mac_address,
                "ip_address": d.ip_address,
                "fw_version": d.fw_version,
                "platform": d.platform,
                "last_activity": d.last_activity.strftime("%Y-%m-%d %H:%M:%S") if d.last_activity else None,
                "timezone": d.timezone,
                "verified": d.verified,
                "initial_sync_completed": d.initial_sync_completed,
                "user_count": d.user_count or 0,
                "transaction_count": d.transaction_count or 0,
                "opd": opd_name,
                "opd_id": opd_id,
                "lokasi": lokasi,
                "registered_by_name": d.registered_by_user.nama_lengkap if d.registered_by_user else None,
                "anti_spoofing_enabled": d.anti_spoofing_enabled if d.anti_spoofing_enabled is not None else True,
            })
        return jsonify(data), 200

    if request.method == 'POST':
        data = request.get_json()

        # Validasi SN wajib
        if not data.get('sn'):
            return jsonify({"error": "Serial Number (sn) wajib diisi."}), 400
        if not data.get('opd_id'):
            return jsonify({"error": "OPD ID wajib diisi."}), 400

        # Cek duplikat SN
        existing = Device.query.get(data['sn'])
        if existing:
            return jsonify({"error": f"Device dengan SN '{data['sn']}' sudah terdaftar."}), 400

        # Buat record di tabel devices (dengan semua field)
        new_device = Device(
            sn=data['sn'],
            name=data.get('name', 'Mesin Absen Kios'),
            device_name=data.get('device_name'),
            mac_address=data.get('mac_address'),
            ip_address=data.get('ip_address'),
            fw_version=data.get('fw_version'),
            platform=data.get('platform'),
            timezone=data.get('timezone', 'Asia/Jakarta'),
            verified=str_to_bool(data.get('verified', True)),
        )
        db.session.add(new_device)
        db.session.flush()  # Flush agar FK di sn_mesin bisa merujuk ke devices.sn

        # Buat record pemetaan di tabel sn_mesin
        new_mapping = SnMesin(
            sn=data['sn'],
            opd_id=data['opd_id'],
            nama_lokasi=data.get('nama_lokasi', '-')
        )
        db.session.add(new_mapping)

        catat_audit(current_user.id, "ADD_DEVICE", "devices",
                    f"Daftar Mesin SN {data['sn']} (IP: {data.get('ip_address', '-')}) ke OPD ID {data['opd_id']}",
                    target_record_id=data['sn'])
        db.session.commit()
        return jsonify({"message": "Mesin berhasil didaftarkan!", "sn": data['sn']}), 201

# ==========================================
# 7. DEVICE BINDING (One-Time Provisioning dari Admin)
# ==========================================
@api_blueprint.route('/devices/bind', methods=['POST'])
@token_required
def bind_device(current_user):
    """
    One-Time Binding: Admin mengikat device kiosk ke OPD-nya.
    
    device_sn, device_name, platform, dll dikirim otomatis oleh mobile app
    (via device_info_plus), BUKAN input manual dari user.
    
    Upsert logic:
      - Jika device_sn sudah ada → update info + bind ke OPD admin
      - Jika device_sn belum ada → insert baru + bind ke OPD admin
    
    Juga upsert tabel user_admin untuk mencatat relasi admin ↔ device.
    
    Request JSON (dari mobile app otomatis):
      { "device_sn": "ABC123XYZ", "device_name": "Samsung SM-T295", 
        "platform": "Android 14", "ip_address": "192.168.1.50",
        "nama_lokasi": "Lobby Gedung A" }
    """
    if current_user.role not in ('super_admin', 'admin_opd'):
        return jsonify({"message": "Akses Ditolak! Hanya Admin yang bisa binding device."}), 403

    data = request.get_json()
    if not data or not data.get('device_sn'):
        return jsonify({"error": "device_sn wajib diisi (dikirim otomatis oleh aplikasi)."}), 400

    device_sn = data['device_sn'].strip()

    # --- Upsert Device ---
    device = Device.query.get(device_sn)
    is_new = device is None

    if is_new:
        device = Device(sn=device_sn)
        db.session.add(device)

    # Update device info dari payload (otomatis dari mobile app)
    device.name = data.get('name', device.name if not is_new else 'Mesin Kiosk')
    device.device_name = data.get('device_name', device.device_name)
    device.platform = data.get('platform', device.platform)
    device.ip_address = data.get('ip_address', device.ip_address)
    device.mac_address = data.get('mac_address', device.mac_address)
    device.fw_version = data.get('fw_version', device.fw_version)
    device.timezone = data.get('timezone', device.timezone or 'Asia/Jakarta')

    # --- Crucial Binding: Link device → OPD admin ---
    device.opd_id = current_user.opd_id
    device.registered_by = current_user.id
    device.verified = True
    device.last_activity = get_wib_time()

    # --- Upsert pemetaan sn_mesin ---
    mapping = SnMesin.query.get(device_sn)
    if not mapping:
        mapping = SnMesin(sn=device_sn, opd_id=current_user.opd_id)
        db.session.add(mapping)
    else:
        mapping.opd_id = current_user.opd_id
    mapping.nama_lokasi = data.get('nama_lokasi', mapping.nama_lokasi or '-')

    # --- Upsert user_admin: Link admin ↔ device (1-to-N) ---
    admin_record = UserAdmin.query.filter_by(
        user_id=current_user.id,
        bound_device_sn=device_sn
    ).first()
    if not admin_record:
        admin_record = UserAdmin(
            user_id=current_user.id,
            bound_device_sn=device_sn
        )
        db.session.add(admin_record)

    # --- Audit Trail ---
    opd_name = current_user.opd.nama_opd if current_user.opd else f"OPD ID {current_user.opd_id}"
    action_detail = f"{'Registrasi baru' if is_new else 'Re-bind'} device SN {device_sn} ke {opd_name} oleh {current_user.nama_lengkap}"
    catat_audit(current_user.id, "BIND_DEVICE", "devices", action_detail, target_record_id=device_sn)

    db.session.commit()

    print(f"\n🔗 [BIND] Device '{device_sn}' → {opd_name} | By: {current_user.nama_lengkap} | {'NEW' if is_new else 'UPDATE'}")

    return jsonify({
        "message": "Device bound successfully.",
        "sn": device.sn,
        "opd_id": device.opd_id,
        "opd_name": opd_name,
        "verified": device.verified,
        "is_new_device": is_new,
        "admin_binding_id": admin_record.id,
    }), 200

# ==========================================
# 7b. DEVICE HEARTBEAT (Auto-report dari Kiosk)
# ==========================================
@api_blueprint.route('/devices/heartbeat', methods=['POST'])
def device_heartbeat():
    """
    Endpoint untuk Flutter Kiosk melaporkan info device-nya secara otomatis.
    Tidak butuh JWT — cukup kirim SN yang sudah terdaftar.
    """
    data = request.get_json()
    if not data or not data.get('sn'):
        return jsonify({"error": "Serial Number (sn) wajib diisi."}), 400

    device = Device.query.get(data['sn'])
    if not device:
        return jsonify({"error": f"Device SN '{data['sn']}' tidak terdaftar di sistem."}), 404

    # Update info device dari data yang dikirim kiosk
    if data.get('ip_address'):
        device.ip_address = data['ip_address']
    if data.get('mac_address'):
        device.mac_address = data['mac_address']
    if data.get('device_name'):
        device.device_name = data['device_name']
    if data.get('platform'):
        device.platform = data['platform']
    if data.get('fw_version'):
        device.fw_version = data['fw_version']
    if data.get('timezone'):
        device.timezone = data['timezone']

    device.last_activity = get_wib_time()
    db.session.commit()

    return jsonify({
        "message": "Heartbeat diterima.",
        "sn": device.sn,
        "verified": device.verified,
        "anti_spoofing_enabled": device.anti_spoofing_enabled if device.anti_spoofing_enabled is not None else True,
    }), 200

# ==========================================
# 8. CRUD OPD (Update & Delete)
# ==========================================
@api_blueprint.route('/opd/<int:id>', methods=['PUT', 'DELETE'])
@token_required
def manage_opd_detail(current_user, id):
    if current_user.role != 'super_admin':
        return jsonify({"message": "Akses Ditolak!"}), 403

    opd = MasterOpd.query.get(id)
    if not opd:
        return jsonify({"error": "OPD tidak ditemukan."}), 404

    if request.method == 'PUT':
        data = request.get_json()
        old_name = opd.nama_opd
        opd.nama_opd = data.get('nama_opd', opd.nama_opd)
        opd.kode_opd = data.get('kode_opd', opd.kode_opd)
        if data.get('alamat_opd') is not None:
            opd.alamat_opd = data['alamat_opd']
        
        catat_audit(current_user.id, "UPDATE_OPD", "master_opd",
                    f"Mengubah OPD '{old_name}' menjadi '{opd.nama_opd}' (Kode: {opd.kode_opd})",
                    target_record_id=str(id))
        db.session.commit()
        return jsonify({"message": f"OPD '{opd.nama_opd}' berhasil diperbarui!"}), 200

    if request.method == 'DELETE':
        # Cek apakah masih ada user yang terhubung ke OPD ini
        user_count = User.query.filter_by(opd_id=id).count()
        if user_count > 0:
            return jsonify({"error": f"Tidak bisa menghapus OPD ini karena masih memiliki {user_count} user terdaftar."}), 400

        # Cek apakah ada mesin yang terhubung
        mesin_count = SnMesin.query.filter_by(opd_id=id).count()
        if mesin_count > 0:
            return jsonify({"error": f"Tidak bisa menghapus OPD ini karena masih memiliki {mesin_count} perangkat terdaftar."}), 400

        nama_opd = opd.nama_opd
        db.session.delete(opd)
        catat_audit(current_user.id, "DELETE_OPD", "master_opd",
                    f"Menghapus OPD: {nama_opd}", target_record_id=str(id))
        return jsonify({"message": f"OPD '{nama_opd}' berhasil dihapus!"}), 200

# ==========================================
# 9. CRUD ADMIN OPD (Update & Delete)
# ==========================================
@api_blueprint.route('/admins/<int:id>', methods=['PUT', 'DELETE'])
@token_required
def manage_admin_detail(current_user, id):
    if current_user.role != 'super_admin':
        return jsonify({"message": "Akses Ditolak!"}), 403

    admin = User.query.get(id)
    if not admin:
        return jsonify({"error": "Admin tidak ditemukan."}), 404
    if admin.role != 'admin_opd':
        return jsonify({"error": "User ini bukan Admin OPD."}), 400

    if request.method == 'PUT':
        data = request.get_json()
        old_name = admin.nama_lengkap
        admin.nama_lengkap = data.get('nama', admin.nama_lengkap)
        if data.get('opd_id'):
            admin.opd_id = data['opd_id']
        if data.get('password'):
            admin.password_hash = generate_password_hash(data['password'])

        catat_audit(current_user.id, "UPDATE_ADMIN", "users",
                    f"Mengubah data Admin OPD: {old_name} → {admin.nama_lengkap}",
                    target_record_id=str(id))
        db.session.commit()
        return jsonify({"message": f"Admin '{admin.nama_lengkap}' berhasil diperbarui!"}), 200

    if request.method == 'DELETE':
        nama_admin = admin.nama_lengkap
        db.session.delete(admin)
        catat_audit(current_user.id, "DELETE_ADMIN", "users",
                    f"Menghapus Admin OPD: {nama_admin} (NIP: {admin.nip})",
                    target_record_id=str(id))
        return jsonify({"message": f"Admin '{nama_admin}' berhasil dihapus!"}), 200

# ==========================================
# 10. CRUD DEVICE (Update & Delete)
# ==========================================
@api_blueprint.route('/devices/<string:sn>', methods=['PUT', 'DELETE'])
@token_required
def manage_device_detail(current_user, sn):
    if current_user.role != 'super_admin':
        return jsonify({"message": "Akses Ditolak!"}), 403

    device = Device.query.get(sn)
    if not device:
        return jsonify({"error": "Device tidak ditemukan."}), 404

    if request.method == 'PUT':
        data = request.get_json()

        # ── Capture old state for change detection ──
        old_anti_spoof = device.anti_spoofing_enabled if device.anti_spoofing_enabled is not None else True

        try:
            device.name = data.get('name', device.name)
            device.device_name = data.get('device_name', device.device_name)
            device.ip_address = data.get('ip_address', device.ip_address)
            device.mac_address = data.get('mac_address', device.mac_address)
            device.platform = data.get('platform', device.platform)
            device.fw_version = data.get('fw_version', device.fw_version)
            device.timezone = data.get('timezone', device.timezone)
            verified_val = data.get('verified')
            if verified_val is not None:
                device.verified = str_to_bool(verified_val)
                
            anti_spoof_val = data.get('anti_spoofing_enabled')
            if anti_spoof_val is not None:
                device.anti_spoofing_enabled = str_to_bool(anti_spoof_val)

            # Update pemetaan sn_mesin jika opd_id atau lokasi berubah
            if data.get('opd_id') or data.get('nama_lokasi'):
                mapping = SnMesin.query.get(sn)
                if mapping:
                    if data.get('opd_id'):
                        mapping.opd_id = data['opd_id']
                    if data.get('nama_lokasi'):
                        mapping.nama_lokasi = data['nama_lokasi']

            # ── Audit: general device update ──
            catat_audit(current_user.id, "UPDATE_DEVICE", "devices",
                        f"Memperbarui info Device SN {sn}",
                        target_record_id=sn, auto_commit=False)

            # ── Audit: anti-spoofing toggle (only if state actually changed) ──
            new_anti_spoof = device.anti_spoofing_enabled
            if new_anti_spoof != old_anti_spoof:
                device_label = device.device_name or device.name or sn
                if new_anti_spoof:
                    detail = f"Mengaktifkan kembali fitur Anti-Spoofing pada perangkat {device_label} (SN: {sn})"
                else:
                    detail = f"Menonaktifkan fitur Anti-Spoofing pada perangkat {device_label} (SN: {sn})"
                
                catat_audit(
                    current_user.id, "TOGGLE_ANTI_SPOOFING", "devices",
                    detail, target_record_id=sn, auto_commit=False
                )
                print(f"\n🛡️ [SECURITY] {detail} | By: {current_user.nama_lengkap} | IP: {request.remote_addr}")

            db.session.commit()
            return jsonify({"message": f"Device '{sn}' berhasil diperbarui!"}), 200

        except Exception as e:
            db.session.rollback()
            print(f"[UPDATE_DEVICE] Error: {e}")
            return jsonify({"error": f"Gagal memperbarui device: {str(e)}"}), 500

    if request.method == 'DELETE':
        # Hapus pemetaan sn_mesin dulu (karena FK ON DELETE CASCADE, tapi aman jika manual)
        mapping = SnMesin.query.get(sn)
        if mapping:
            db.session.delete(mapping)
        db.session.delete(device)
        catat_audit(current_user.id, "DELETE_DEVICE", "devices",
                    f"Menghapus Device SN: {sn} (IP: {device.ip_address or '-'})",
                    target_record_id=sn)
        return jsonify({"message": f"Device '{sn}' berhasil dihapus!"}), 200

# ==========================================
# 10b. UNBIND DEVICE (Super Admin / Admin OPD yang memiliki)
# ==========================================
@api_blueprint.route('/devices/<string:sn>/unbind', methods=['PUT'])
@token_required
def unbind_device(current_user, sn):
    """
    Putuskan ikatan perangkat dari instansi.
    
    Akses:
      - super_admin: bisa unbind semua perangkat
      - admin_opd: hanya bisa unbind perangkat milik OPD-nya sendiri
    
    Efek:
      - verified = False
      - opd_id = None
      - registered_by = None
      - Perangkat masih ada di database, tapi tidak bisa dipakai presensi
    """
    device = Device.query.get(sn)
    if not device:
        return jsonify({"error": "Device tidak ditemukan."}), 404

    # RBAC: super_admin = all, admin_opd = own OPD only
    if current_user.role == 'admin_opd':
        if device.opd_id != current_user.opd_id:
            return jsonify({"error": "Anda hanya dapat melepas perangkat milik instansi Anda."}), 403
    elif current_user.role != 'super_admin':
        return jsonify({"error": "Akses Ditolak!"}), 403

    old_opd_id = device.opd_id
    old_opd_name = "-"
    if old_opd_id:
        old_opd = MasterOpd.query.get(old_opd_id)
        old_opd_name = old_opd.nama_opd if old_opd else f"OPD #{old_opd_id}"

    # Unbind: putuskan ikatan
    device.verified = False
    device.opd_id = None
    device.registered_by = None

    # Hapus juga UserAdmin binding yang terkait
    UserAdmin.query.filter_by(device_sn=sn).delete()

    # Audit Trail
    catat_audit(
        current_user.id, "UNBIND_DEVICE", "devices",
        f"Melepas ikatan Device SN: {sn} dari instansi: {old_opd_name} (OPD #{old_opd_id})",
        target_record_id=sn
    )
    db.session.commit()

    print(f"\n🔓 [UNBIND] Device {sn} dilepas dari {old_opd_name} oleh {current_user.nama_lengkap}")
    return jsonify({
        "message": f"Perangkat '{sn}' berhasil dilepas dari instansi {old_opd_name}.",
        "sn": sn
    }), 200

# ==========================================
# 11. AUDIT TRAIL (Read Only — Tidak bisa diubah/dihapus)
# ==========================================
@api_blueprint.route('/audit-logs', methods=['GET'])
@token_required
def get_audit_logs(current_user):
    if current_user.role != 'super_admin': 
        return jsonify({"message": "Akses Ditolak"}), 403
    
    # Ambil 100 log terakhir, urutkan dari yang paling baru
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(100).all()
    data = []
    for log in logs:
        # Resolve actor name
        actor_name = None
        if log.actor_user_id:
            actor = User.query.get(log.actor_user_id)
            actor_name = actor.nama_lengkap if actor else f"User #{log.actor_user_id}"
        data.append({
            "log_id": log.log_id,
            "actor_id": log.actor_user_id,
            "actor_name": actor_name,
            "action": log.action,
            "target": log.target_table,
            "detail": log.keterangan_detail,
            "waktu": log.created_at.strftime("%Y-%m-%d %H:%M:%S")
        })
    
    return jsonify(data), 200

# ==========================================
# JADWAL KEGIATAN — CRUD + Presensi Endpoints
# ==========================================

@api_blueprint.route('/kegiatan', methods=['POST'])
@token_required
def create_kegiatan(current_user):
    """Buat kegiatan baru dengan undangan per-OPD."""
    if current_user.role not in ('admin_opd', 'super_admin'):
        return jsonify({"error": "Akses Ditolak."}), 403
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Payload JSON wajib diisi."}), 400

        required = ['nama_kegiatan', 'tanggal_mulai', 'tanggal_selesai']
        for field in required:
            if field not in data or data[field] is None:
                return jsonify({"error": f"Field '{field}' wajib diisi."}), 400

        try:
            tgl_mulai = datetime.strptime(data['tanggal_mulai'], '%Y-%m-%d').date()
            tgl_selesai = datetime.strptime(data['tanggal_selesai'], '%Y-%m-%d').date()
        except ValueError:
            return jsonify({"error": "Format tanggal harus YYYY-MM-DD."}), 400
        if tgl_selesai < tgl_mulai:
            return jsonify({"error": "tanggal_selesai tidak boleh sebelum tanggal_mulai."}), 400

        is_global = bool(data.get('is_global', False))
        target_opd_id = None if current_user.role == 'super_admin' else current_user.opd_id

        jam_mulai, jam_selesai = None, None
        if data.get('jam_mulai'):
            try: jam_mulai = datetime.strptime(data['jam_mulai'], '%H:%M').time()
            except ValueError: return jsonify({"error": "Format jam_mulai harus HH:MM."}), 400
        if data.get('jam_selesai'):
            try: jam_selesai = datetime.strptime(data['jam_selesai'], '%H:%M').time()
            except ValueError: return jsonify({"error": "Format jam_selesai harus HH:MM."}), 400

        lat = data.get('latitude_target')
        lng = data.get('longitude_target')

        kegiatan = JadwalKegiatan(
            nama_kegiatan=data['nama_kegiatan'], keterangan=data.get('keterangan', ''),
            alamat_lokasi=data.get('alamat_lokasi', ''),
            latitude_target=float(lat) if lat else None,
            longitude_target=float(lng) if lng else None,
            radius_toleransi=int(data.get('radius_toleransi', 100)),
            tanggal_mulai=tgl_mulai, tanggal_selesai=tgl_selesai,
            jam_mulai=jam_mulai, jam_selesai=jam_selesai,
            is_global=is_global, opd_id=target_opd_id, created_by=current_user.id
        )
        db.session.add(kegiatan)
        db.session.flush()

        invited_opd_ids = data.get('invited_opd_ids', [])
        if not is_global and invited_opd_ids:
            for oid in invited_opd_ids:
                db.session.add(UndanganKegiatan(kegiatan_id=kegiatan.id, opd_id=int(oid)))
        db.session.commit()

        jumlah_opd = UndanganKegiatan.query.filter_by(kegiatan_id=kegiatan.id).count()
        catat_audit(current_user.id, 'CREATE_KEGIATAN', 'jadwal_kegiatan',
            f"Membuat kegiatan '{kegiatan.nama_kegiatan}' ({'GLOBAL' if is_global else 'INTERNAL'}) undangan {jumlah_opd} OPD",
            target_record_id=str(kegiatan.id))

        return jsonify({"message": "Jadwal kegiatan berhasil dibuat.", "kegiatan_id": kegiatan.id,
            "is_global": is_global, "jumlah_opd_diundang": jumlah_opd}), 201
    except Exception as e:
        db.session.rollback()
        print(f"\u274c [CREATE_KEGIATAN] Error: {e}")
        return jsonify({"error": f"Gagal membuat kegiatan: {str(e)}"}), 500


@api_blueprint.route('/kegiatan', methods=['GET'])
@token_required
def get_kegiatan(current_user):
    """Daftar kegiatan. Super Admin=semua, Admin OPD=Global+diundang."""
    if current_user.role not in ('admin_opd', 'super_admin'):
        return jsonify({"error": "Akses Ditolak."}), 403
    # pyrefly: ignore [missing-import]
    from sqlalchemy import or_
    if current_user.role == 'super_admin':
        query = JadwalKegiatan.query
    else:
        invited_ids = [u.kegiatan_id for u in UndanganKegiatan.query.filter_by(opd_id=current_user.opd_id).all()]
        conditions = [JadwalKegiatan.is_global == True, JadwalKegiatan.opd_id == current_user.opd_id]
        if invited_ids:
            conditions.append(JadwalKegiatan.id.in_(invited_ids))
        query = JadwalKegiatan.query.filter(or_(*conditions))

    kegiatan_list = query.order_by(JadwalKegiatan.tanggal_mulai.desc()).all()
    result = []
    for k in kegiatan_list:
        invited_opds = [{"id": u.opd_id, "nama_opd": u.opd.nama_opd if u.opd else "?"} for u in k.undangan_opd]
        hadir_count = PresensiKegiatan.query.filter_by(kegiatan_id=k.id).count()
        result.append({
            "id": k.id, "nama_kegiatan": k.nama_kegiatan, "keterangan": k.keterangan,
            "alamat_lokasi": k.alamat_lokasi, "latitude_target": k.latitude_target,
            "longitude_target": k.longitude_target, "radius_toleransi": k.radius_toleransi,
            "tanggal_mulai": k.tanggal_mulai.strftime('%Y-%m-%d'),
            "tanggal_selesai": k.tanggal_selesai.strftime('%Y-%m-%d'),
            "jam_mulai": k.jam_mulai.strftime('%H:%M') if k.jam_mulai else None,
            "jam_selesai": k.jam_selesai.strftime('%H:%M') if k.jam_selesai else None,
            "is_global": k.is_global, "opd_id": k.opd_id,
            "invited_opds": invited_opds, "jumlah_opd_diundang": len(invited_opds),
            "jumlah_hadir": hadir_count,
            "created_at": k.created_at.strftime('%Y-%m-%d %H:%M:%S') if k.created_at else None,
        })
    return jsonify(result), 200


@api_blueprint.route('/kegiatan/<int:id>', methods=['DELETE'])
@token_required
def delete_kegiatan(current_user, id):
    """Hapus kegiatan beserta undangan + presensi (cascade)."""
    if current_user.role not in ('admin_opd', 'super_admin'):
        return jsonify({"error": "Akses Ditolak."}), 403
    try:
        kegiatan = JadwalKegiatan.query.get(id)
        if not kegiatan:
            return jsonify({"error": "Kegiatan tidak ditemukan."}), 404
        if current_user.role == 'admin_opd':
            if kegiatan.is_global:
                return jsonify({"error": "Kegiatan Global hanya bisa dihapus Super Admin."}), 403
            if kegiatan.opd_id != current_user.opd_id:
                return jsonify({"error": "Kegiatan ini bukan milik OPD Anda."}), 403
        nama = kegiatan.nama_kegiatan
        db.session.delete(kegiatan)
        db.session.commit()
        catat_audit(current_user.id, 'DELETE_KEGIATAN', 'jadwal_kegiatan',
            f"Menghapus kegiatan '{nama}'", target_record_id=str(id))
        return jsonify({"message": f"Kegiatan '{nama}' berhasil dihapus."}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Gagal menghapus kegiatan: {str(e)}"}), 500


@api_blueprint.route('/kegiatan/active', methods=['GET'])
def get_active_kegiatan():
    """Kegiatan aktif hari ini — untuk dropdown kiosk Flutter. No auth."""
    from models import get_wib_time
    now = get_wib_time()
    today, ct = now.date(), now.time()
    all_active = JadwalKegiatan.query.filter(
        JadwalKegiatan.tanggal_mulai <= today, JadwalKegiatan.tanggal_selesai >= today
    ).order_by(JadwalKegiatan.jam_mulai.asc()).all()
    result = []
    for k in all_active:
        if k.jam_mulai and ct < k.jam_mulai: continue
        if k.jam_selesai and ct > k.jam_selesai: continue
        result.append({"id": k.id, "nama_kegiatan": k.nama_kegiatan,
            "alamat_lokasi": k.alamat_lokasi, "is_global": k.is_global,
            "jam_mulai": k.jam_mulai.strftime('%H:%M') if k.jam_mulai else None,
            "jam_selesai": k.jam_selesai.strftime('%H:%M') if k.jam_selesai else None})
    return jsonify(result), 200


@api_blueprint.route('/predict/kegiatan', methods=['POST'])
def predict_kegiatan():
    """Presensi kegiatan via face scan + OPD validation + duplicate check."""
    if 'photo' not in request.files:
        return jsonify({"error": "Image file is required"}), 400
    device_klien_sn = request.form.get("device_sn", "WEB_APP_01")
    kegiatan_id = request.form.get("kegiatan_id", type=int)
    if not kegiatan_id:
        return jsonify({"error": "kegiatan_id wajib diisi."}), 400

    kegiatan = JadwalKegiatan.query.get(kegiatan_id)
    if not kegiatan:
        return jsonify({"error": "Kegiatan tidak ditemukan."}), 404

    from models import get_wib_time
    now = get_wib_time()
    today = now.date()
    if not (kegiatan.tanggal_mulai <= today <= kegiatan.tanggal_selesai):
        return jsonify({"error": "Kegiatan tidak aktif hari ini."}), 403
    if kegiatan.jam_mulai and now.time() < kegiatan.jam_mulai:
        return jsonify({"error": f"Kegiatan belum dimulai (mulai {kegiatan.jam_mulai.strftime('%H:%M')})."}), 403
    if kegiatan.jam_selesai and now.time() > kegiatan.jam_selesai:
        return jsonify({"error": f"Kegiatan sudah berakhir (selesai {kegiatan.jam_selesai.strftime('%H:%M')})."}), 403

    photo = request.files['photo']
    if not allowed_file(photo.filename):
        return jsonify({"error": "File type not allowed."}), 400

    temp_filename = f"{uuid4().hex}.jpg"
    image_path = os.path.join(TEMP_DIR, temp_filename)
    photo.save(image_path)
    test_embedding = get_embedding(image_path)
    if test_embedding is None:
        return jsonify({"error": "Gagal mendeteksi wajah."}), 500

    best_nip, best_name, best_similarity = "unknown", "unknown", 0.0
    for folder_name in os.listdir(EMBEDDINGS_DIR):
        pkl_path = os.path.join(EMBEDDINGS_DIR, folder_name, f"{folder_name}.pkl")
        txt_path = os.path.join(EMBEDDINGS_DIR, folder_name, f"{folder_name}.txt")
        if not os.path.exists(pkl_path) or not os.path.exists(txt_path): continue
        with open(pkl_path, "rb") as f:
            known_embeddings = pickle.load(f)
        similarity = compare_faces(test_embedding, known_embeddings, THRESHOLD)
        if similarity > best_similarity:
            best_similarity = similarity
            best_nip, best_name = read_txt(txt_path)

    if best_nip == "unknown" or best_similarity < THRESHOLD:
        pct = float(round(best_similarity * 100, 1))
        print(f"\n\U0001f534 [KEGIATAN] UNKNOWN FACE | Similarity: {pct}%")
        return jsonify({"error": "UNKNOWN_FACE", "message": "Wajah tidak dikenali."}), 401

    similarity_pct = float(round(best_similarity * 100, 1))
    user = User.query.filter_by(nip=best_nip).first()
    if not user:
        return jsonify({"error": "User tidak ditemukan."}), 404

    # OPD Validation
    if not kegiatan.is_global:
        invited = [u.opd_id for u in UndanganKegiatan.query.filter_by(kegiatan_id=kegiatan_id).all()]
        if user.opd_id not in invited:
            opd_name = user.opd.nama_opd if user.opd else "?"
            print(f"\n\U0001f7e1 [KEGIATAN] OPD DITOLAK: {best_name} ({opd_name})")
            return jsonify({"error": "OPD_NOT_INVITED",
                "message": f"Instansi Anda ({opd_name}) tidak diundang ke kegiatan ini."}), 403

    # Duplicate check
    existing = PresensiKegiatan.query.filter_by(kegiatan_id=kegiatan_id, nip=best_nip).first()
    if existing:
        print(f"\n\U0001f7e1 [KEGIATAN] DUPLIKAT: {best_name}")
        return jsonify({"nip": best_nip, "name": best_name,
            "status": "Anda sudah tercatat hadir pada kegiatan ini.",
            "is_duplicate": True, "kegiatan": kegiatan.nama_kegiatan,
            "waktu": existing.waktu_scan.strftime("%H:%M:%S")}), 200

    # Insert
    lat_scan = request.form.get('latitude_scan', type=float)
    lng_scan = request.form.get('longitude_scan', type=float)
    new_record = PresensiKegiatan(kegiatan_id=kegiatan_id, nip=best_nip,
        waktu_scan=now, device_sn=device_klien_sn,
        latitude_scan=lat_scan, longitude_scan=lng_scan)
    db.session.add(new_record)
    db.session.commit()
    print(f"\n\U0001f7e2 [KEGIATAN] HADIR: {best_name} | {similarity_pct}% | {kegiatan.nama_kegiatan}")
    return jsonify({"nip": best_nip, "name": best_name,
        "status": "Kehadiran Kegiatan Berhasil", "kegiatan": kegiatan.nama_kegiatan,
        "waktu": now.strftime("%H:%M:%S"), "is_duplicate": False}), 200


@api_blueprint.route('/report/kegiatan', methods=['GET'])
@token_required
def report_kegiatan(current_user):
    """Laporan presensi kegiatan dengan pagination + tenant isolation."""
    if current_user.role not in ('admin_opd', 'super_admin'):
        return jsonify({"error": "Akses Ditolak."}), 403

    kegiatan_id = request.args.get('kegiatan_id', type=int)
    search = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    query = db.session.query(PresensiKegiatan, DataPegawai, JadwalKegiatan, User
    ).join(DataPegawai, PresensiKegiatan.nip == DataPegawai.nip
    ).join(JadwalKegiatan, PresensiKegiatan.kegiatan_id == JadwalKegiatan.id
    ).outerjoin(User, User.nip == PresensiKegiatan.nip)

    if kegiatan_id:
        query = query.filter(PresensiKegiatan.kegiatan_id == kegiatan_id)
    if current_user.role == 'admin_opd':
        query = query.filter(User.opd_id == current_user.opd_id)
    if search:
        query = query.filter(db.or_(
            DataPegawai.nama_lengkap.ilike(f'%{search}%'),
            DataPegawai.nip.ilike(f'%{search}%')))

    total = query.count()
    records = query.order_by(PresensiKegiatan.waktu_scan.desc()).offset((page-1)*per_page).limit(per_page).all()

    data = []
    for pk, pegawai, kg, usr in records:
        opd_name = usr.opd.nama_opd if usr and usr.opd else '-'
        data.append({"id": pk.id, "nip": pk.nip, "nama_lengkap": pegawai.nama_lengkap,
            "opd": opd_name, "kegiatan_id": kg.id, "nama_kegiatan": kg.nama_kegiatan,
            "waktu_scan": pk.waktu_scan.strftime('%Y-%m-%d %H:%M:%S'), "device_sn": pk.device_sn})

    return jsonify({"data": data, "total_records": total, "current_page": page,
        "per_page": per_page, "total_pages": math.ceil(total / per_page) if per_page > 0 else 1}), 200


