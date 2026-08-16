"""One-time migration: backfill username for existing admin accounts."""
from sqlalchemy import text
from app import app
from models import db

with app.app_context():
    conn = db.engine.connect()
    result = conn.execute(text(
        "UPDATE users SET username = user_nip WHERE role IN ('super_admin', 'admin_opd') AND username IS NULL"
    ))
    conn.commit()
    conn.close()
    print(f"✅ Backfilled username for {result.rowcount} admin(s)")
