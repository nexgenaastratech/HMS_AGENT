import os, sqlite3
from app.core.config import settings
from app.services.memory import USE_SQLITE, init_db

db_path = settings.SQLITE_DB_PATH
print(f"DB path   : {db_path}")
print(f"USE_SQLITE: {USE_SQLITE}")

existed = os.path.exists(db_path)
print(f"DB existed before init: {existed}")

# Explicitly call init_db (also runs at import time)
init_db()

print(f"DB exists now : {os.path.exists(db_path)}")
print(f"DB size       : {os.path.getsize(db_path)} bytes")

conn = sqlite3.connect(db_path)
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
conn.close()

print(f"\nTables found ({len(tables)}):")
for t in tables:
    print(f"  [OK] {t[0]}")
