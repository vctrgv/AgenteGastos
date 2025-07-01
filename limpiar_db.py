import sqlite3

conn = sqlite3.connect("gastos.db")
cursor = conn.cursor()

cursor.execute("DELETE FROM gastos")
conn.commit()

print("✅ Tabla 'gastos' limpiada correctamente.")

conn.close()
