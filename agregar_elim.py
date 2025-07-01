import sqlite3

conn = sqlite3.connect("gastos.db")
cursor = conn.cursor()
cursor.execute("ALTER TABLE gastos ADD COLUMN eliminado INTEGER DEFAULT 0")
conn.commit()
conn.close()
