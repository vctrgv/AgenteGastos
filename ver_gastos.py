import sqlite3
import pandas as pd

# Conectar a la base de datos
conn = sqlite3.connect("gastos.db")
cursor = conn.cursor()

# Leer todos los registros
query = "SELECT id, fecha, descripcion, monto, celular, eliminado FROM gastos ORDER BY fecha DESC"
df = pd.read_sql_query(query, conn)

conn.close()

# Mostrar los resultados
print("\n📋 Registros actuales en la tabla 'gastos':\n")
print(df.to_string(index=False))
