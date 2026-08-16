from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import pytz
from werkzeug.security import check_password_hash
from sqlalchemy import BigInteger, Sequence

def get_wib_time():
    tz = pytz.timezone('Asia/Jakarta')
    return datetime.now(tz)

db = SQLAlchemy()

# 1. Tabel Jangkar OPD
class MasterOpd(db.Model):
    __tablename__ = 'master_opd'
    id = db.Column(db.Integer, primary_key=True)
    nama_opd = db.Column(db.String(100), nullable=False)
    kode_opd = db.Column(db.String(50), unique=True, nullable=False)
    alamat_opd = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=get_wib_time)
    
    # Relasi ORM
    users = db.relationship('User', backref='opd', lazy=True)
    mesin = db.relationship('SnMesin', backref='opd', lazy=True)

# 2. Tabel Data Pegawai Mentah
class DataPegawai(db.Model):
    __tablename__ = 'data_pegawai'
    id = db.Column(db.Integer, primary_key=True)
    pin = db.Column(db.String(50), unique=True, nullable=False)
    nip = db.Column(db.String(50), unique=True, nullable=False)
    nama_lengkap = db.Column(db.String(100), nullable=False)

# 3a. Tabel Hardware (13 kolom sesuai tabel `devices` di database)
class Device(db.Model):
    __tablename__ = 'devices'
    sn = db.Column(db.String(50), primary_key=True)
    name = db.Column(db.String(100))
    device_name = db.Column(db.String(100))
    mac_address = db.Column(db.String(50))
    ip_address = db.Column(db.String(50))
    fw_version = db.Column(db.String(50))
    platform = db.Column(db.String(50))
    last_activity = db.Column(db.DateTime)
    timezone = db.Column(db.String(50), default='Asia/Jakarta')
    verified = db.Column(db.Boolean, default=False)
    initial_sync_completed = db.Column(db.Boolean, default=False)
    user_count = db.Column(db.Integer, default=0)
    transaction_count = db.Column(db.Integer, default=0)
    opd_id = db.Column(db.Integer, db.ForeignKey('master_opd.id'), nullable=True)
    registered_by = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=True)
    anti_spoofing_enabled = db.Column(db.Boolean, default=True, nullable=False)
    
    pemetaan = db.relationship('SnMesin', backref='device_info', uselist=False, lazy=True)
    opd = db.relationship('MasterOpd', backref=db.backref('devices', lazy=True), foreign_keys=[opd_id])
    registered_by_user = db.relationship('User', backref=db.backref('registered_devices', lazy=True), foreign_keys=[registered_by])

# 3b. Tabel Pemetaan Lokasi Hardware
class SnMesin(db.Model):
    __tablename__ = 'sn_mesin'
    sn = db.Column(db.String(50), db.ForeignKey('devices.sn'), primary_key=True)
    opd_id = db.Column(db.Integer, db.ForeignKey('master_opd.id'), nullable=False)
    nama_lokasi = db.Column(db.String(100))

# 4. Tabel Pengguna Aktif & RBAC
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column('user_id', db.Integer, primary_key=True)
    nip = db.Column('user_nip', db.String(50), db.ForeignKey('data_pegawai.nip', ondelete='SET NULL'), nullable=True)
    pin = db.Column('user_pin', db.String(50), nullable=True)
    nama_lengkap = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(100), unique=True, nullable=True)  # Login credential (terpisah dari NIP)
    opd_id = db.Column(db.Integer, db.ForeignKey('master_opd.id'), nullable=True)
    role = db.Column(db.String(20), nullable=False, default='asn') 
    password_hash = db.Column(db.String(255), nullable=True)
    is_face_registered = db.Column(db.Boolean, default=False)
    approval_status = db.Column(db.String(20), default='approved')  # 'pending', 'approved', 'rejected'
    created_at = db.Column(db.DateTime, default=get_wib_time)

    # Menghubungkan user_pin ke tabel presensi dengan Logical Primary Join
    presensi = db.relationship('Presensi', primaryjoin="User.pin == Presensi.user_pin", foreign_keys="[Presensi.user_pin]", backref='pegawai', lazy=True)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# 4b. Tabel Akses Lintas Instansi (Cross-OPD Face Registration)
class UserAksesOpd(db.Model):
    __tablename__ = 'user_akses_opd'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_nip = db.Column(db.String(50), db.ForeignKey('data_pegawai.nip'), nullable=False, index=True)
    opd_id = db.Column(db.Integer, db.ForeignKey('master_opd.id'), nullable=False)
    approval_status = db.Column(db.String(20), default='approved')  # 'pending', 'approved', 'rejected'
    created_at = db.Column(db.DateTime, default=get_wib_time)

    # Unique constraint: satu NIP hanya boleh punya satu record per OPD
    __table_args__ = (
        db.UniqueConstraint('user_nip', 'opd_id', name='uq_user_nip_opd_id'),
    )

    # Relasi ORM
    opd = db.relationship('MasterOpd', backref=db.backref('akses_users', lazy=True))

# 4c. Tabel Admin-Device Binding (Normalisasi relasi admin ↔ kiosk)
class UserAdmin(db.Model):
    __tablename__ = 'user_admin'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    bound_device_sn = db.Column(db.String(50), db.ForeignKey('devices.sn'), nullable=True)
    created_at = db.Column(db.DateTime, default=get_wib_time)

    # Relasi ORM (1 Admin → N Devices, 1 Device → N Admin bindings)
    user = db.relationship('User', backref=db.backref('admin_bindings', lazy=True))
    device = db.relationship('Device', backref=db.backref('bound_admins', lazy=True))

# 5. Tabel Audit Log
class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    log_id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=True)
    action = db.Column(db.String(50), nullable=False)
    target_table = db.Column(db.String(50))
    target_record_id = db.Column(db.String(50), nullable=False, default="-")
    ip_address = db.Column(db.String(50))
    keterangan_detail = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=get_wib_time)

# 6. Tabel Presensi Transaksional
class Presensi(db.Model):
    __tablename__ = 'presensi'
    log_id = db.Column(db.BigInteger, Sequence('presensi_log_id_seq'), primary_key=True, autoincrement=True)
    user_pin = db.Column(db.String(50), nullable=False, index=True) 
    device_sn = db.Column(db.String(50), nullable=False, default='WEB_APP') 
    waktu_scan = db.Column('waktu_presensi', db.DateTime, primary_key=True, default=get_wib_time) 
    tipe_absen = db.Column(db.String(10), nullable=False) 
    status_kehadiran = db.Column(db.String(20), default='ON_TIME')
    keterlambatan_menit = db.Column(db.Integer, default=0)
    # ── Kolom baru untuk Jadwal Kegiatan (Geofencing) ──
    latitude_scan = db.Column(db.Float, nullable=True)
    longitude_scan = db.Column(db.Float, nullable=True)
    kegiatan_id = db.Column(db.Integer, db.ForeignKey('jadwal_kegiatan.id'), nullable=True)

# 7. Tabel Pengaturan Sistem (Key-Value)
class AppSetting(db.Model):
    __tablename__ = 'app_settings'
    setting_key = db.Column(db.String(50), primary_key=True)
    setting_value = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=get_wib_time, onupdate=get_wib_time)

    @staticmethod
    def get(key, default=None):
        """Helper: fetch a setting value by key."""
        row = AppSetting.query.get(key)
        return row.setting_value if row else default

# 8. Tabel Hari Libur Custom
class HariLiburCustom(db.Model):
    __tablename__ = 'hari_libur_custom'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tanggal = db.Column(db.Date, unique=True, nullable=False)
    keterangan = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=get_wib_time)

# 9. Tabel Jadwal Kegiatan (Out-of-Office Activity)
class JadwalKegiatan(db.Model):
    __tablename__ = 'jadwal_kegiatan'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nama_kegiatan = db.Column(db.String(150), nullable=False)
    keterangan = db.Column(db.Text)
    alamat_lokasi = db.Column(db.Text)
    latitude_target = db.Column(db.Float, nullable=True)
    longitude_target = db.Column(db.Float, nullable=True)
    radius_toleransi = db.Column(db.Integer, default=100)  # dalam meter
    tanggal_mulai = db.Column(db.Date, nullable=False)
    tanggal_selesai = db.Column(db.Date, nullable=False)
    jam_mulai = db.Column(db.Time, nullable=True)   # Time boundary: attendance opens
    jam_selesai = db.Column(db.Time, nullable=True)  # Time boundary: attendance closes
    is_global = db.Column(db.Boolean, default=False, nullable=False)  # True = semua OPD boleh
    opd_id = db.Column(db.Integer, db.ForeignKey('master_opd.id'), nullable=True)  # Creator's OPD (NULL = Global)
    created_by = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    created_at = db.Column(db.DateTime, default=get_wib_time)
    
    # Relasi ORM dengan cascade delete
    undangan_opd = db.relationship('UndanganKegiatan', backref='kegiatan', lazy=True, cascade='all, delete-orphan')
    presensi_kegiatan = db.relationship('PresensiKegiatan', backref='kegiatan', lazy=True, cascade='all, delete-orphan')
    presensi_harian = db.relationship('Presensi', backref='kegiatan', lazy=True)
    opd = db.relationship('MasterOpd', backref=db.backref('kegiatan_list', lazy=True), foreign_keys=[opd_id])

# 10. Tabel Undangan Kegiatan per-OPD (Many-to-Many Bridge)
class UndanganKegiatan(db.Model):
    __tablename__ = 'undangan_kegiatan'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    kegiatan_id = db.Column(db.Integer, db.ForeignKey('jadwal_kegiatan.id'), nullable=False)
    opd_id = db.Column(db.Integer, db.ForeignKey('master_opd.id'), nullable=False)
    
    # Relasi ORM
    opd = db.relationship('MasterOpd', backref=db.backref('undangan_kegiatan', lazy=True))
    
    # Unique constraint: satu OPD hanya bisa diundang sekali per kegiatan
    __table_args__ = (
        db.UniqueConstraint('kegiatan_id', 'opd_id', name='uq_kegiatan_opd'),
    )

# 11. Tabel Presensi Kegiatan (Log Kehadiran per-Event)
class PresensiKegiatan(db.Model):
    __tablename__ = 'presensi_kegiatan'
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    kegiatan_id = db.Column(db.Integer, db.ForeignKey('jadwal_kegiatan.id'), nullable=False)
    nip = db.Column(db.String(50), db.ForeignKey('data_pegawai.nip'), nullable=False)
    waktu_scan = db.Column(db.DateTime, default=get_wib_time, nullable=False)
    device_sn = db.Column(db.String(50), nullable=False)
    latitude_scan = db.Column(db.Float, nullable=True)
    longitude_scan = db.Column(db.Float, nullable=True)
    
    # Relasi ORM
    pegawai = db.relationship('DataPegawai', backref=db.backref('presensi_kegiatan_list', lazy=True))
    
    # Unique constraint: satu NIP hanya bisa presensi sekali per kegiatan
    __table_args__ = (
        db.UniqueConstraint('kegiatan_id', 'nip', name='uq_presensi_kegiatan_nip'),
    )

