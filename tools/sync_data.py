import os
from app import app
from models import db, User, DataPegawai, MasterOpd
from config.config import EMBEDDINGS_DIR

def sync_legacy_data():
    with app.app_context():
        print("🔄 Memulai sinkronisasi data ASN & Wajah dari folder embeddings...")

        # Pastikan OPD Diskominfo (OPD-001) sudah ada
        opd = MasterOpd.query.filter_by(kode_opd="OPD-001").first()
        if not opd:
            print("❌ OPD Diskominfo belum ada! Akses URL /api/init-super-admin di browser terlebih dahulu.")
            return

        if not os.path.exists(EMBEDDINGS_DIR):
            print(f"❌ Folder {EMBEDDINGS_DIR} tidak ditemukan!")
            return

        added_pegawai_count = 0
        added_user_count = 0
        skipped_count = 0

        for folder_name in os.listdir(EMBEDDINGS_DIR):
            folder_path = os.path.join(EMBEDDINGS_DIR, folder_name)
            
            if os.path.isdir(folder_path):
                txt_path = os.path.join(folder_path, f"{folder_name}.txt")
                
                if os.path.exists(txt_path):
                    with open(txt_path, 'r') as f:
                        # Membersihkan data kotor (jika ada tanda kurung siku)
                        raw_text = f.read().strip()
                        clean_text = raw_text.replace('[', '').replace(']', '')
                        data = clean_text.split(',')
                        
                        if len(data) >= 2:
                            nip = data[0].strip()
                            nama = data[1].strip()
                            
                            # 1. CEK DATA MASTER (data_pegawai)
                            pegawai = DataPegawai.query.filter_by(nip=nip).first()
                            
                            # Jika ASN Diskominfo ini belum ada di data_pegawai (karena dari web)
                            if not pegawai:
                                dummy_pin = f"WEB-{nip[:10]}" # Buatkan PIN Dummy agar DB tidak error (NOT NULL constraint)
                                pegawai = DataPegawai(
                                    pin=dummy_pin,
                                    nip=nip,
                                    nama_lengkap=nama
                                )
                                db.session.add(pegawai)
                                db.session.flush() # Eksekusi sementara ke DB agar ID-nya siap dipakai
                                added_pegawai_count += 1
                                print(f"📝 Master Data Baru: {nama} ({nip}) - Dibuatkan PIN: {dummy_pin}")

                            # 2. MASUKKAN KE TABEL USERS (Sistem Web)
                            existing_user = User.query.filter_by(nip=nip).first()
                            if not existing_user:
                                new_user = User(
                                    nip=nip,
                                    pin=pegawai.pin,
                                    nama_lengkap=nama,
                                    role='asn',
                                    opd_id=opd.id, # Masukkan otomatis ke Diskominfo
                                    is_face_registered=True # Tandai bahwa wajahnya sudah tersimpan di folder
                                )
                                db.session.add(new_user)
                                added_user_count += 1
                                print(f"✅ User Disinkronisasi: {nama}")
                            else:
                                # Jika sebelumnya is_face_registered masih False, kita Update menjadi True
                                if not existing_user.is_face_registered:
                                    existing_user.is_face_registered = True
                                skipped_count += 1
                                print(f"⏭️ Melewati: {nama} (Sudah ada di tabel Users)")

        # 3. SIMPAN SEMUA PERUBAHAN
        if added_pegawai_count > 0 or added_user_count > 0:
            db.session.commit()
            print(f"\n🎉 Sinkronisasi Selesai!")
            print(f"📊 Menambahkan ke Data Pegawai: {added_pegawai_count} orang")
            print(f"📊 Menambahkan ke User Aktif : {added_user_count} orang")
        else:
            print(f"\n✅ Sinkronisasi Selesai! Tidak ada data wajah baru. {skipped_count} ASN sudah tersinkron.")

if __name__ == "__main__":
    sync_legacy_data()