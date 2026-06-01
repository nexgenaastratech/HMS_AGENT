import sqlite3
import json

db_path = r"c:\Users\nexge\Music\Projects\Chatbot\chats_v2.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT * FROM notification_logs ORDER BY created_at DESC LIMIT 5;")
rows = cursor.fetchall()
print("NOTIFICATION LOGS:")
for row in rows:
    print(row)

cursor.execute("SELECT * FROM conversations WHERE wa_id LIKE '%7540062368%' LIMIT 5;")
rows = cursor.fetchall()
print("\nCONVERSATIONS:")
for row in rows:
    print(row)

conn.close()
