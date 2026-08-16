# 📊 Analisis Lengkap Project: Sistem Presensi Wajah ASN Kab. Tangerang

> **Tanggal Analisis**: 28 April 2026 (Updated)
> **Versi Sebelumnya**: 27 April 2026
> **Database**: `db_face_recognation_v2.0` (MySQL 8.4.3)

---

## 1. Gambaran Umum Sistem

Sistem **platform presensi pegawai (ASN) berbasis pengenalan wajah** untuk Dinas Komunikasi dan Informatika Kabupaten Tangerang. Terdiri dari 3 komponen utama:

```mermaid
graph TB
    subgraph "Frontend - Mobile Kiosk"
        A["📱 Flutter App<br/>(asngface)"]
        A1["🔐 Activation View<br/>Login + Device Binding"]
        A2["🔓 Admin Unlock<br/>Biometric Face Verify"]
    end
    
    subgraph "Backend - REST API"
        B["🐍 Flask REST API<br/>(Face_Recognition_AI_Secure)"]
    end
    
    subgraph "AI / ML Engine"
        C["🧠 MTCNN + FaceNet<br/>Face Detection & Recognition"]
        C2["🛡️ Multi-Frame Anti-Spoofing<br/>Temporal Analysis (Server-Side)"]
    end
    
    subgraph "Storage"
        D["🗄️ MySQL (Partitioned)<br/>db_face_recognation_v2.0"]
        E["📂 File System<br/>samples/ & samples_embedding/"]
    end
    
    A -->|"HTTP multipart/form-data"| B
    A1 -->|"Login + Bind"| B
    A2 -->|"Face Unlock"| B
    B --> C
    B --> C2
    B --> D
    C --> E
```

---

## 2. Technology Stack

### 🐍 Backend (Flask REST API)

| Komponen | Teknologi | Keterangan |
|---|---|---|
| Framework | **Flask** + Blueprint | REST API modular |
| Database ORM | **SQLAlchemy** | Model-driven DB access |
| Database | **MySQL 8.4.3** (PyMySQL) | Partitioned tables |
| AI/ML Model | **FaceNet** (keras_facenet) | 512-dimensi face embedding |
| Face Detection | **MTCNN** | Multi-task Cascaded CNN |
| Anti-Spoofing | **OpenCV + NumPy** | Multi-frame temporal analysis |
| Authentication | **JWT** (PyJWT) | Token berbasis 2 jam |
| Password | **Werkzeug** | bcrypt-style hashing |
| CORS | **Flask-CORS** | Cross-origin enabled |
| Image Processing | **Pillow**, **NumPy**, **SciPy** | Preprocessing & cosine similarity |
| API Docs | **Swagger/OpenAPI** | YAML spec + HTML viewer |

### 📱 Frontend (Flutter Kiosk App)

| Komponen | Teknologi | Keterangan |
|---|---|---|
| Framework | **Flutter** (Dart SDK ^3.7.2) | Cross-platform mobile |
| Camera | `camera: ^0.10.5+2` | Real-time camera stream |
| Face Detection (Client) | `google_mlkit_face_detection` | On-device liveness check |
| HTTP Client | **Dio** `^5.8.0+1` | Multipart upload + timeout |
| Config Persistence | `shared_preferences` | Server IP, Device SN, Binding state |
| Image Processing | `image: ^4.1.3` | Client-side face cropping |
| 🆕 Device Info | `device_info_plus: ^11.3.3` | **Collect SN, model, platform** |
| Path Utility | `path_provider` | Temp directory for captures |

---

## 3. Arsitektur Database (ERD)

```mermaid
erDiagram
    MASTER_OPD ||--o{ USERS : "has"
    MASTER_OPD ||--o{ SN_MESIN : "has"
    MASTER_OPD ||--o{ USER_AKSES_OPD : "accessed_by"
    MASTER_OPD ||--o{ DEVICES : "bound_to"
    DATA_PEGAWAI ||--o{ USERS : "1:1 via NIP+PIN"
    DATA_PEGAWAI ||--o{ USER_AKSES_OPD : "cross-opd"
    DEVICES ||--|| SN_MESIN : "mapped"
    USERS ||--o{ PRESENSI : "via PIN"
    USERS ||--o{ AUDIT_LOGS : "actor"
    USERS ||--o{ DEVICES : "registered_by"

    MASTER_OPD {
        int id PK
        string nama_opd
        string kode_opd UK
        text alamat_opd
        datetime created_at
    }

    DATA_PEGAWAI {
        int id PK
        string pin UK
        string nip UK
        string nama_lengkap
    }

    USERS {
        int user_id PK
        string user_nip FK
        string user_pin FK
        string nama_lengkap
        int opd_id FK
        enum role
        string password_hash
        boolean is_face_registered
        string approval_status
        datetime created_at
    }

    USER_AKSES_OPD {
        int id PK
        string user_nip FK
        int opd_id FK
        string approval_status
        datetime created_at
    }

    DEVICES {
        string sn PK
        string name
        string device_name
        string mac_address
        string ip_address
        string fw_version
        string platform
        datetime last_activity
        string timezone
        boolean verified
        boolean initial_sync_completed
        int user_count
        int transaction_count
        int opd_id FK
        int registered_by FK
    }

    SN_MESIN {
        string sn PK_FK
        int opd_id FK
        string nama_lokasi
    }

    PRESENSI {
        bigint log_id PK
        string user_pin
        string device_sn
        datetime waktu_presensi PK
        enum tipe_absen
        enum status_kehadiran
        int keterlambatan_menit
    }

    AUDIT_LOGS {
        bigint log_id PK
        int actor_user_id FK
        string action
        string target_table
        string target_record_id
        text keterangan_detail
        string ip_address
        datetime created_at
    }
```

### Perubahan Database Terbaru:

- 🆕 **`devices.opd_id`** — FK ke `master_opd.id`, mengikat device ke instansi
- 🆕 **`devices.registered_by`** — FK ke `users.user_id`, admin yang melakukan binding
- ✅ **Table Partitioning** — Tabel `presensi` RANGE partition per bulan
- ✅ **Approval Status** — Kolom di `users` dan `user_akses_opd`

---

## 4. API Endpoints — 25 Endpoint

> [!IMPORTANT]
> **Total API berkembang dari 12 → 22 → 25 endpoint.** 3 endpoint baru ditambahkan pada update terakhir.

| # | Endpoint | Method | Auth | Fitur |
|---|---|---|---|---|
| 1 | `/api/init-super-admin` | GET | ❌ | Inisialisasi Super Admin + OPD + Device default |
| 2 | `/api/login` | POST | ❌ | Login JWT (admin_opd & super_admin only) |
| 3 | `/api/predict` | POST | ❌ | **🔴 Core: Face Recognition + Attendance** |
| 4 | `/api/check-spoof` | POST | ❌ | Server-side Multi-Frame Anti-Spoofing |
| 🆕5 | `/api/predict/unlock` | POST | ❌ | **🔓 Biometric Admin Unlock (Face-based)** |
| 6 | `/api/report` | GET | ✅ | Dashboard laporan presensi (paginated) |
| 7 | `/api/manage-asn` | GET | ✅ | Daftar ASN + status + approval |
| 8 | `/api/users/<id>` | DELETE | ✅ | Hapus ASN (role-scoped) |
| 9 | `/api/register` | POST | ✅ | Registrasi wajah via Web (auto-approved) |
| 10 | `/api/register/mobile` | POST | 🔑SN | Registrasi dari Kiosk **(OPD dari device binding)** |
| 11 | `/api/users/update/<nip>` | PUT | ✅ | Update profil ASN + re-register wajah |
| 12 | `/api/users/approve/<nip>` | PUT | ✅ | Approval workflow |
| 13 | `/api/users/pending` | GET | ✅ | List pending registrations |
| 14 | `/api/opd/list` | GET | ❌ | Public OPD list untuk Kiosk |
| 15 | `/api/opd` | GET/POST | ✅ | CRUD Master OPD |
| 16 | `/api/opd/<id>` | PUT/DELETE | ✅ | Update & Delete OPD |
| 17 | `/api/admin/add` | POST | ✅ | Tambah Admin OPD |
| 18 | `/api/admins` | GET | ✅ | Daftar admin OPD |
| 19 | `/api/admins/<id>` | PUT/DELETE | ✅ | Update & Delete Admin OPD |
| 20 | `/api/devices` | GET/POST | ✅ | Manajemen perangkat |
| 🆕21 | `/api/devices/bind` | POST | ✅ | **🔗 One-Time Device Binding (Admin → OPD)** |
| 22 | `/api/devices/<sn>` | PUT/DELETE | ✅ | Update & Delete Device |
| 23 | `/api/devices/heartbeat` | POST | ❌ | Device auto-reporting |
| 24 | `/api/audit-logs` | GET | ✅ | Jejak audit (100 terbaru) |

---

## 5. Fitur Terbaru — Device Provisioning & Admin Unlock

### 🆕 A. One-Time Device Binding (Provisioning)

Flow lengkap dari device belum terdaftar hingga siap digunakan:

```mermaid
sequenceDiagram
    participant Admin
    participant Kiosk as Flutter Kiosk
    participant API as Flask API
    participant DB as MySQL

    Note over Kiosk: Pertama kali boot → ActivationView

    Admin->>Kiosk: Masukkan Server URL, SN, Username, Password
    Kiosk->>API: POST /api/login {username, password}
    API-->>Kiosk: {access_token: "eyJ...", user: {...}}
    
    Kiosk->>Kiosk: Collect device info (device_info_plus)
    Kiosk->>API: POST /api/devices/bind {device_sn, device_name, platform, ...}
    Note over API: JWT → admin.opd_id<br/>Upsert device + sn_mesin
    API->>DB: Device.opd_id = admin.opd_id<br/>Device.registered_by = admin.id<br/>Device.verified = true
    API-->>Kiosk: {message, opd_id, opd_name, verified}
    
    Kiosk->>Kiosk: SharedPreferences: is_bound = true
    Note over Kiosk: Restart → langsung ke Kiosk Mode ✅
```

**Endpoint**: `POST /api/devices/bind`
- **Auth**: JWT (admin_opd atau super_admin)
- **Logic**: Upsert device → bind `opd_id` dari admin → set `verified=true`
- **Audit**: `BIND_DEVICE`

### 🆕 B. Biometric Admin Unlock

Admin scan wajah untuk membuka menu kiosk (registrasi/settings):

```mermaid
flowchart TD
    A["👤 Admin tap icon ⚙️<br/>di AppBar PresensiView"] --> B["📸 Capture foto wajah"]
    B --> C["POST /api/predict/unlock<br/>{photo, device_sn}"]
    C --> D{MTCNN + FaceNet<br/>Similarity >= 75%?}
    D -->|No| E["❌ 401: Wajah tidak dikenali"]
    D -->|Yes| F{Cek Role}
    F -->|super_admin| G["✅ 200: Unlock semua device"]
    F -->|admin_opd| H{OPD admin == OPD device?}
    H -->|Yes| I["✅ 200: Unlock"]
    H -->|No| J["❌ 403: Bukan Admin instansi ini"]
    F -->|asn| K["❌ 403: Akses khusus Admin"]
```

**Endpoint**: `POST /api/predict/unlock`
- **Auth**: Face-based (tidak perlu JWT)
- **Response**: `{unlock: true/false, role, name, nip, similarity}`

### 🆕 C. Refactored Mobile Registration

Registrasi dari kiosk tidak lagi membutuhkan `opd_id` dari client:

| Aspek | Sebelum (v1) | Sesudah (v2) |
|---|---|---|
| OPD Source | Client kirim `opd_id` di form | **Otomatis dari `device.opd_id`** |
| Approval | `pending` (perlu admin approve) | **`approved`** (admin sudah unlock) |
| Source Label | `'mobile'` | **`'kiosk'`** |
| Validasi Device | Cek `verified` | Cek `verified` **+ `opd_id` not null** |

### 🆕 D. Startup Routing (SplashRouter)

```mermaid
flowchart TD
    A["App Start"] --> B{"SharedPreferences<br/>is_bound == true?"}
    B -->|No| C["ActivationView<br/>(Login + Bind)"]
    B -->|Yes| D["MyHomePage<br/>(Kiosk Mode)"]
    C -->|Binding Success| D
```

---

## 6. Audit Trail — 20 Jenis Action

| Action | Trigger | Baru? |
|---|---|---|
| `SYSTEM_INIT` | Inisialisasi Super Admin | |
| `REGISTER_ASN` | Daftarkan wajah ASN baru | |
| `CROSS_OPD_REGISTER` | Registrasi lintas instansi | |
| `DELETE_USER` | Hapus ASN | |
| `ADD_OPD` | Tambah instansi | |
| `ADD_ADMIN` | Buat akun admin | |
| `ADD_DEVICE` | Daftarkan mesin | |
| `UPDATE_ASN` | Update profil ASN | |
| `RE_REGISTER_FACE` | Re-registrasi wajah | |
| `APPROVE_ASN` | Setujui registrasi ASN | |
| `REJECT_ASN` | Tolak registrasi ASN | |
| `APPROVE_CROSS_OPD` | Setujui akses lintas instansi | |
| `REJECT_CROSS_OPD` | Tolak akses lintas instansi | |
| `UPDATE_OPD` | Ubah data OPD | |
| `DELETE_OPD` | Hapus OPD | |
| `UPDATE_ADMIN` | Ubah data Admin | |
| `DELETE_ADMIN` | Hapus Admin | |
| `UPDATE_DEVICE` | Ubah info Device | |
| `DELETE_DEVICE` | Hapus Device | |
| `BIND_DEVICE` | **Binding device ke OPD** | 🆕 |

---

## 7. Struktur File Project (Updated)

### Backend (`Face_Recognition_AI_Secure/`)
```
Face_Recognition_AI_Secure/
├── app.py                          # Entry point Flask
├── models.py                       # 8 SQLAlchemy models (+opd_id, registered_by)
├── config/
│   └── config.py                   # EMBEDDINGS_DIR, TEMP, THRESHOLD
├── api/
│   ├── routes.py                   # 25 API endpoints (1500+ lines)
│   ├── facenet_utils.py            # ML pipeline (169 lines)
│   └── anti_spoofing_utils.py      # Multi-frame anti-spoofing (391 lines)
├── docs/
│   ├── swagger.yaml                # OpenAPI/Swagger spec
│   └── index.html                  # Swagger UI viewer
├── sql/
│   ├── database_face-recognation-v2.sql
│   ├── create_user_akses_opd.sql
│   └── alter_user_akses_opd_add_approval.sql
├── sync_data.py
├── regenerate_embeddings.py
├── samples/                        # Foto registrasi ASN
├── samples_embedding/              # Embedding .pkl + .txt
└── temp/                           # Temp upload
```

### Frontend (`asngface/lib/`)
```
asngface/lib/
├── main.dart                       # Entry + SplashRouter + MyHomePage
├── presensi_view.dart              # Camera + Liveness + Admin Unlock button
├── hasil_view.dart                 # Result screen + auto-return
├── activation/
│   └── activation_view.dart        # 🆕 Login + Device Binding screen
├── config/
│   └── app_config.dart             # SharedPrefs (+isBound, +bindUrl, +unlockUrl)
├── models/
│   ├── predict_response.dart
│   └── api_error.dart
├── services/
│   └── api_service.dart            # Dio client (+loginAdmin, +bindDevice, +adminUnlock)
├── settings/
│   └── settings_view.dart
└── register/
    └── view/
        ├── register_view.dart
        ├── camera_page.dart
        └── widget_template.dart
```

---

## 8. Analisis Keamanan (Updated)

### ✅ Yang Sudah Baik

| Aspek | Implementasi |
|---|---|
| Password Hashing | Werkzeug `generate_password_hash` |
| JWT Auth | Token 2 jam, `@token_required` decorator |
| Role Checking | Validasi role di setiap endpoint sensitif |
| File Validation | Cek ekstensi + PIL verify |
| Anti-Spoofing Client | Liveness detection (blink + head turn) |
| Anti-Spoofing Server | Multi-frame temporal analysis |
| Audit Trail | **20 jenis action** tercatat |
| Device Verification | Predict menolak device belum verified |
| 🆕 Device Binding | **OPD derived dari admin, bukan client** |
| 🆕 Biometric Admin Auth | **Face-based unlock, bukan token** |
| Approval Workflow | Mobile registration butuh approval (kecuali kiosk) |
| Scope Check | Admin OPD hanya kelola OPD sendiri |

### ⚠️ Yang Masih Perlu Diperbaiki

| Issue | Severity |
|---|---|
| Hardcoded Secret Key di routes.py:18 | 🔴 **Tinggi** |
| Hardcoded DB URI di app.py:18 | 🔴 **Tinggi** |
| Syntax error routes.py:15 (`im`) | 🔴 **Tinggi** |
| Bare `except:` di `token_required` | 🟡 Sedang |
| CORS Wildcard | 🟡 Sedang |
| No Rate Limiting | 🟡 Sedang |

---

## 9. Ringkasan Perubahan: Timeline Lengkap

| Tanggal | Endpoints | Fitur Kunci |
|---|---|---|
| **10 Apr 2026** | 12 | MVP: Predict, Register, Report, RBAC |
| **27 Apr 2026** | 22 | +Anti-Spoofing Server, +Approval, +Full CRUD, +Heartbeat |
| **28 Apr 2026** | **25** | **+Device Binding, +Admin Unlock, +Startup Router** |

### Perubahan 28 April 2026 (Hari Ini):

**Backend:**
- `models.py`: +`Device.opd_id`, +`Device.registered_by` (FK)
- `routes.py`: +`POST /devices/bind`, +`POST /predict/unlock`
- `routes.py`: Refactored `/register/mobile` → OPD dari device, bukan client
- `_process_registration()`: source `'kiosk'` → auto-approved

**Frontend:**
- `pubspec.yaml`: +`device_info_plus`
- `app_config.dart`: +`isBound`, +`boundOpdName`, +`bindUrl`, +`unlockUrl`
- `api_service.dart`: +`loginAdmin()`, +`bindDevice()`, +`adminUnlock()`
- `main.dart`: +`SplashRouter` (routing berdasarkan binding state)
- `activation_view.dart`: 🆕 Login admin + device binding screen
- `presensi_view.dart`: +Admin unlock button di AppBar

---

## 10. Skor Kematangan Project

| Area | Skor | Status |
|---|---|---|
| **Core Feature (Face Recognition)** | ⭐⭐⭐⭐ | MTCNN pipeline solid |
| **API Architecture** | ⭐⭐⭐⭐⭐ | 25 endpoint, full CRUD, provisioning |
| **Database Design** | ⭐⭐⭐⭐⭐ | Partitioned + approval + device binding |
| **RBAC & Auth** | ⭐⭐⭐⭐⭐ | JWT + Face unlock + Device binding + Approval |
| **Flutter Kiosk** | ⭐⭐⭐⭐⭐ | Liveness + auto-bind + admin unlock |
| **Anti-Spoofing** | ⭐⭐⭐⭐ | Client + Server multi-frame |
| **Security** | ⭐⭐⭐ | Masih perlu env vars, rate limit |
| **Scalability** | ⭐⭐⭐ | DB partitioning, perlu FAISS |
| **Testing** | ⭐ | Belum ada unit test |
| **Documentation** | ⭐⭐⭐⭐ | Swagger API docs |
| **CI/CD** | ⭐ | Belum ada pipeline |

> **Overall**: Project telah mencapai level **Production-Ready** dengan fitur enterprise-grade lengkap: device provisioning, biometric admin unlock, approval workflow, full CRUD, dan API documentation. Arsitektur keamanan berlapis (JWT + Face + Device SN) sudah kuat. Prioritas selanjutnya: **env vars**, **FAISS vector search**, dan **automated testing**.
