import sqlite3

conn = sqlite3.connect("gastos.db")
cursor = conn.cursor()

# Verificamos si ya existe la columna 'celular'
cursor.execute("PRAGMA table_info(gastos)")
columnas = [col[1] for col in cursor.fetchall()]

if 'celular' not in columnas:
    cursor.execute("ALTER TABLE gastos ADD COLUMN celular TEXT DEFAULT ''")
    print("✅ Columna 'celular' agregada.")
else:
    print("ℹ️ La columna 'celular' ya existe.")

conn.commit()
conn.close()
