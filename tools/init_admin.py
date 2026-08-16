from api.facenet_utils import load_users, save_users, hash_password

# Untuk buat user admin pertama kali / tambah user admin
users = load_users()
# Username
users["admin"] = {
    # Password
    "password": hash_password("..."),
    "role": "admin"
}
save_users(users)
print("Admin user created.")
