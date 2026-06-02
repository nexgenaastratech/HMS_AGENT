import sqlite3
import json

conn = sqlite3.connect('chatbot.db')
c = conn.cursor()
c.execute('SELECT conversation FROM conversations')
rows = c.fetchall()
if rows:
    msgs = json.loads(rows[0][0])
    for m in msgs[-6:]:
        print(f"{m['role'].upper()}: {m['content']}")
else:
    print('No conversation found')
