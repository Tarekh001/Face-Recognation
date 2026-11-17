from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import pytz
from werkzeug.security import check_password_hash


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

    # Relasi ORM ke 2 domain tabel user (ASN & Non-ASN)
    users = db.relationship('UserAsn', backref='opd', lazy=True)
    users_non_asn = db.relationship('UserNonAsn', backref='opd', lazy=True)
    mesin = db.relationship('SnMesin', backref='opd', lazy=True)


# 2. Tabel Data Pegawai Mentah (Master Induk ASN dari SPOT)
class DataPegawai(db.Model):
    __tablename__ = 'data_pegawai'
    id = db.Column(db.Integer, primary_key=True)
    pin = db.Column(db.String(50), unique=True, nullable=False)
    nip = db.Column(db.String(50), unique=True, nullable=False)
    nama_lengkap = db.Column(db.String(100), nullable=False)


# 3a. Tabel Hardware Kiosk
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
    registered_by = db.Column(db.Integer, db.ForeignKey('users_asn.user_id', ondelete='SET NULL'), nullable=True)
    anti_spoofing_enabled = db.Column(db.Boolean, default=True, nullable=False)

    pemetaan = db.relationship('SnMesin', backref='device_info', uselist=False, lazy=True)
    opd = db.relationship('MasterOpd', backref=db.backref('devices', lazy=True), foreign_keys=[opd_id])
    registered_by_user = db.relationship('UserAsn', backref=db.backref('registered_devices', lazy=True), foreign_keys=[registered_by])


# 3b. Tabel Pemetaan Lokasi Hardware
class SnMesin(db.Model):
    __tablename__ = 'sn_mesin'
    sn = db.Column(db.String(50), db.ForeignKey('devices.sn'), primary_key=True)
    opd_id = db.Column(db.Integer, db.ForeignKey('master_opd.id'), nullable=False)
    nama_lokasi = db.Column(db.String(100))


# 4a. Tabel Pengguna ASN & Admin Portal (Terikat Ketat ke data_pegawai SPOT)
class UserAsn(db.Model):
    __tablename__ = 'users_asn'
    id = db.Column('user_id', db.Integer, primary_key=True)
    nip = db.Column('nip', db.String(50), db.ForeignKey('data_pegawai.nip', onupdate='CASCADE', ondelete='RESTRICT'), unique=True, nullable=False)
    pin = db.Column('pin', db.String(50), nullable=False)
    nama_lengkap = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(100), unique=True, nullable=True)
    opd_id = db.Column(db.Integer, db.ForeignKey('master_opd.id', ondelete='SET NULL'), nullable=True)
    role = db.Column(db.String(20), nullable=False, default='asn')  # 'asn' | 'admin_opd' | 'super_admin'
    password_hash = db.Column(db.String(255), nullable=True)
    is_face_registered = db.Column(db.Boolean, default=False, nullable=False)
    approval_status = db.Column(db.String(20), default='approved', nullable=False)
    jam_kerja_id = db.Column(db.Integer, db.ForeignKey('master_jam_kerja.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=get_wib_time)

    presensi_list = db.relationship('PresensiAsn', backref='pegawai_asn', lazy=True, cascade='all, delete-orphan')
    jam_kerja_default = db.relationship('MasterJamKerja', foreign_keys=[jam_kerja_id], lazy=True)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)


# Alias kompatibilitas untuk autentikasi admin/RBAC
User = UserAsn


# 4b. Tabel Pengguna Tenaga Non-ASN (Mandiri per OPD berbasis NIK 16 Digit)
class UserNonAsn(db.Model):
    __tablename__ = 'users_non_asn'
    id = db.Column('non_asn_id', db.Integer, primary_key=True)
    nik = db.Column('nik', db.String(16), unique=True, nullable=False)
    nama_lengkap = db.Column(db.String(100), nullable=False)
    opd_id = db.Column(db.Integer, db.ForeignKey('master_opd.id', ondelete='RESTRICT'), nullable=False)
    jam_kerja_id = db.Column(db.Integer, db.ForeignKey('master_jam_kerja.id', ondelete='SET NULL'), nullable=True)
    is_face_registered = db.Column(db.Boolean, default=False, nullable=False)
    approval_status = db.Column(db.String(20), default='approved', nullable=False)
    created_at = db.Column(db.DateTime, default=get_wib_time)

    presensi_list = db.relationship('PresensiNonAsn', backref='pegawai_non_asn', lazy=True, cascade='all, delete-orphan', foreign_keys='PresensiNonAsn.non_asn_id')
    jam_kerja_default = db.relationship('MasterJamKerja', foreign_keys=[jam_kerja_id], lazy=True)

    @property
    def nip(self):
        return self.nik

    @nip.setter
    def nip(self, value):
        self.nik = value

    @property
    def pin(self):
        return None

    @property
    def role(self):
        return 'non_asn'


# 4c. Tabel Akses Lintas Instansi (Khusus ASN)
class UserAksesOpd(db.Model):
    __tablename__ = 'user_akses_opd'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_nip = db.Column(db.String(50), db.ForeignKey('users_asn.nip', onupdate='CASCADE', ondelete='CASCADE'), nullable=False, index=True)
    opd_id = db.Column(db.Integer, db.ForeignKey('master_opd.id'), nullable=False)
    approval_status = db.Column(db.String(20), default='approved')
    created_at = db.Column(db.DateTime, default=get_wib_time)

    __table_args__ = (
        db.UniqueConstraint('user_nip', 'opd_id', name='uq_user_nip_opd_id'),
    )

    opd = db.relationship('MasterOpd', backref=db.backref('akses_users', lazy=True))


# 4d. Tabel Admin-Device Binding
class UserAdmin(db.Model):
    __tablename__ = 'user_admin'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users_asn.user_id', ondelete='CASCADE'), nullable=False)
    bound_device_sn = db.Column(db.String(50), db.ForeignKey('devices.sn'), nullable=True)
    created_at = db.Column(db.DateTime, default=get_wib_time)

    user = db.relationship('UserAsn', backref=db.backref('admin_bindings', lazy=True))
    device = db.relationship('Device', backref=db.backref('bound_admins', lazy=True))


# 5. Tabel Audit Log
class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    log_id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey('users_asn.user_id', ondelete='SET NULL'), nullable=True)
    action = db.Column(db.String(50), nullable=False)
    target_table = db.Column(db.String(50))
    target_record_id = db.Column(db.String(50), nullable=False, default='-')
    ip_address = db.Column(db.String(50))
    keterangan_detail = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=get_wib_time)


# 6a. Tabel Presensi Reguler ASN (Selaras Dashboard & Siap Kirim ke SPOT)
class PresensiAsn(db.Model):
    __tablename__ = 'presensi_asn'
    log_id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users_asn.user_id', ondelete='CASCADE'), nullable=False)
    nip = db.Column(db.String(50), db.ForeignKey('data_pegawai.nip', onupdate='CASCADE'), nullable=False, index=True)
    user_pin = db.Column(db.String(50), nullable=False, index=True)  # PIN SPOT asli dari data_pegawai.pin
    nama_lengkap = db.Column(db.String(100), nullable=False)
    opd_id = db.Column(db.Integer, db.ForeignKey('master_opd.id', ondelete='SET NULL'), nullable=True)
    jam_kerja_id = db.Column(db.Integer, db.ForeignKey('master_jam_kerja.id', ondelete='SET NULL'), nullable=True)
    tanggal_tugas = db.Column(db.Date, nullable=False, index=True)
    waktu_scan = db.Column(db.DateTime, nullable=False, default=get_wib_time)
    tipe_absen = db.Column(db.String(3), nullable=False)  # 'IN' | 'OUT'
    status_kehadiran = db.Column(db.String(20), nullable=False, default='ON_TIME')  # 'ON_TIME' | 'LATE'
    keterlambatan_menit = db.Column(db.Integer, nullable=False, default=0)
    device_sn = db.Column(db.String(50), nullable=False, default='WEB_APP')
    foto_presensi = db.Column(db.Text, nullable=True)
    spot_sync_status = db.Column(db.String(20), nullable=False, default='pending')  # 'pending' | 'synced' | 'failed'
    spot_synced_at = db.Column(db.DateTime, nullable=True)
    spot_response = db.Column(db.Text, nullable=True)

    jam_kerja = db.relationship('MasterJamKerja', foreign_keys=[jam_kerja_id], lazy=True)
    opd = db.relationship('MasterOpd', foreign_keys=[opd_id], lazy=True)


# Alias kompatibilitas default
Presensi = PresensiAsn


# 6b. Tabel Presensi Reguler Non-ASN (Selaras Dashboard Internal OPD)
class PresensiNonAsn(db.Model):
    __tablename__ = 'presensi_non_asn'
    log_id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    non_asn_id = db.Column(db.Integer, db.ForeignKey('users_non_asn.non_asn_id', ondelete='CASCADE'), nullable=False)
    nik = db.Column(db.String(16), db.ForeignKey('users_non_asn.nik', onupdate='CASCADE', ondelete='CASCADE'), nullable=False, index=True)
    nama_lengkap = db.Column(db.String(100), nullable=False)
    opd_id = db.Column(db.Integer, db.ForeignKey('master_opd.id', ondelete='CASCADE'), nullable=False)
    jam_kerja_id = db.Column(db.Integer, db.ForeignKey('master_jam_kerja.id', ondelete='SET NULL'), nullable=True)
    tanggal_tugas = db.Column(db.Date, nullable=False, index=True)
    waktu_scan = db.Column(db.DateTime, nullable=False, default=get_wib_time)
    tipe_absen = db.Column(db.String(3), nullable=False)  # 'IN' | 'OUT'
    status_kehadiran = db.Column(db.String(20), nullable=False, default='ON_TIME')  # 'ON_TIME' | 'LATE'
    keterlambatan_menit = db.Column(db.Integer, nullable=False, default=0)
    device_sn = db.Column(db.String(50), nullable=False, default='WEB_APP')
    foto_presensi = db.Column(db.Text, nullable=True)

    jam_kerja = db.relationship('MasterJamKerja', foreign_keys=[jam_kerja_id], lazy=True)
    opd = db.relationship('MasterOpd', foreign_keys=[opd_id], lazy=True)

    @property
    def nip(self):
        return self.nik

    @property
    def user_pin(self):
        return self.nik


# 7. Tabel Pengaturan Sistem (Key-Value)
class AppSetting(db.Model):
    __tablename__ = 'app_settings'
    setting_key = db.Column(db.String(50), primary_key=True)
    setting_value = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=get_wib_time, onupdate=get_wib_time)

    @staticmethod
    def get(key, default=None):
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
    radius_toleransi = db.Column(db.Integer, default=100)
    tanggal_mulai = db.Column(db.Date, nullable=False)
    tanggal_selesai = db.Column(db.Date, nullable=False)
    jam_mulai = db.Column(db.Time, nullable=True)
    jam_selesai = db.Column(db.Time, nullable=True)
    is_global = db.Column(db.Boolean, default=False, nullable=False)
    opd_id = db.Column(db.Integer, db.ForeignKey('master_opd.id'), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users_asn.user_id'), nullable=False)
    created_at = db.Column(db.DateTime, default=get_wib_time)

    undangan_opd = db.relationship('UndanganKegiatan', backref='kegiatan', lazy=True, cascade='all, delete-orphan')
    presensi_kegiatan = db.relationship('PresensiKegiatan', backref='kegiatan', lazy=True, cascade='all, delete-orphan')
    opd = db.relationship('MasterOpd', backref=db.backref('kegiatan_list', lazy=True), foreign_keys=[opd_id])


# 10. Tabel Undangan Kegiatan per-OPD
class UndanganKegiatan(db.Model):
    __tablename__ = 'undangan_kegiatan'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    kegiatan_id = db.Column(db.Integer, db.ForeignKey('jadwal_kegiatan.id'), nullable=False)
    opd_id = db.Column(db.Integer, db.ForeignKey('master_opd.id'), nullable=False)

    opd = db.relationship('MasterOpd', backref=db.backref('undangan_kegiatan', lazy=True))

    __table_args__ = (
        db.UniqueConstraint('kegiatan_id', 'opd_id', name='uq_kegiatan_opd'),
    )


# 11. Tabel Presensi Kegiatan (Log Kehadiran per-Event)
class PresensiKegiatan(db.Model):
    __tablename__ = 'presensi_kegiatan'
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    kegiatan_id = db.Column(db.Integer, db.ForeignKey('jadwal_kegiatan.id'), nullable=False)
    nip = db.Column(db.String(50), nullable=False)
    waktu_scan = db.Column(db.DateTime, default=get_wib_time, nullable=False)
    device_sn = db.Column(db.String(50), nullable=False)
    latitude_scan = db.Column(db.Float, nullable=True)
    longitude_scan = db.Column(db.Float, nullable=True)

    __table_args__ = (
        db.UniqueConstraint('kegiatan_id', 'nip', name='uq_presensi_kegiatan_nip'),
    )


# 12. Tabel Master Jam Kerja (Multi-Shift & Jam Kerja OPD)
class MasterJamKerja(db.Model):
    __tablename__ = 'master_jam_kerja'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nama_shift = db.Column(db.String(100), nullable=False)
    jam_masuk = db.Column(db.Time, nullable=False)
    jam_pulang = db.Column(db.Time, nullable=False)
    mulai_scan_masuk = db.Column(db.Time, nullable=False)
    akhir_scan_masuk = db.Column(db.Time, nullable=False)
    mulai_scan_pulang = db.Column(db.Time, nullable=False)
    akhir_scan_pulang = db.Column(db.Time, nullable=False)
    menit_toleransi = db.Column(db.Integer, default=0, nullable=False)
    is_lintas_hari = db.Column(db.Boolean, default=False, nullable=False)
    abaikan_libur = db.Column(db.Boolean, default=False, nullable=False)
    opd_id = db.Column(db.Integer, db.ForeignKey('master_opd.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=get_wib_time)

    opd = db.relationship('MasterOpd', backref=db.backref('jam_kerja_list', lazy=True), foreign_keys=[opd_id])


# 13. Tabel Roster Jadwal Shift Bergulir (Mendukung ASN via user_id & Non-ASN via non_asn_id)
class RosterJadwalShift(db.Model):
    __tablename__ = 'roster_jadwal_shift'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users_asn.user_id', ondelete='CASCADE'), nullable=True, index=True)
    non_asn_id = db.Column(db.Integer, db.ForeignKey('users_non_asn.non_asn_id', ondelete='CASCADE'), nullable=True, index=True)
    tanggal = db.Column(db.Date, nullable=False, index=True)
    jam_kerja_id = db.Column(db.Integer, db.ForeignKey('master_jam_kerja.id', ondelete='RESTRICT'), nullable=False)
    keterangan = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=get_wib_time)

    user = db.relationship('UserAsn', backref=db.backref('roster_list', lazy=True, cascade='all, delete-orphan'), foreign_keys=[user_id])
    user_non_asn = db.relationship('UserNonAsn', backref=db.backref('roster_list', lazy=True, cascade='all, delete-orphan'), foreign_keys=[non_asn_id])
    jam_kerja = db.relationship('MasterJamKerja', backref=db.backref('roster_entries', lazy=True))

    __table_args__ = (
        db.UniqueConstraint('user_id', 'tanggal', name='uq_roster_user_tanggal'),
    )
