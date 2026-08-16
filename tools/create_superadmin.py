from app import app
from models import User, db
from werkzeug.security import generate_password_hash

def seed_super_admin():
    # Gunakan context dari aplikasi Flask kita
    with app.app_context():
        # 1. Cek apakah Super Admin sudah ada agar tidak duplikat
        existing_admin = User.query.filter_by(nip='admin01').first()
        
        if existing_admin:
            print("Super Admin sudah ada di database!")
            return

        # 2. Buat password yang dienkripsi (Hashing)
        # Jangan pernah menyimpan teks asli seperti "rahasia123" di database
        hashed_password = generate_password_hash('anakmagangdariumn003')

        # 3. Buat objek User baru
        super_admin = User(
            nip='Admin001', # Username untuk login
            nama_lengkap='Muhamad Tarekh',
            password_hash=hashed_password,
            role='super_admin' # Role tertinggi
        )

        # 4. Masukkan ke database
        db.session.add(super_admin)
        db.session.commit()
        

if __name__ == "__main__":
    seed_super_admin()
        
