import psycopg2

conn = psycopg2.connect(host='localhost', port=5434, user='postgres', password='apalah123', dbname='db_face_recognation_v3.0')
cur = conn.cursor()

print("=== user_akses_opd (Cross-OPD Records) ===")
cur.execute("SELECT * FROM user_akses_opd ORDER BY id DESC LIMIT 10")
rows = cur.fetchall()
for row in rows:
    print(f"  {row}")

if not rows:
    print("  (Kosong - belum ada data cross-OPD)")

conn.close()
