import pytesseract
from PIL import Image
import re
import sqlite3
from datetime import datetime 
import os 

IMAGENES_PATH = 'tickets'

conn = sqlite3.connect('gastos.db')
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS gastos (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               fecha TEXT, 
               descripcion TEXT,
               monto REAL, 
               fuente_imagen TEXT,
               creado_en DATETIME DEFAULT CURRENT_TIMESTAMP
               )
               """)
conn.commit()

def parse_float(texto):
    texto = texto.strip()
    if ',' in texto and '.' not in texto:
        texto = texto.replace(',','.')
    return float(re.sub(r'[^\d.]','',texto))

def extraer_info(texto):
    lineas = texto.strip().split('\n')

    monto = 0
    for linea in lineas:
        if 'total' in linea.lower():
            match = re.search(r'(\d{1,4}[.,]?\d{2})', linea)
            if match:
                monto = parse_float(match.group(1))
                break
    
    if monto == 0:
        posibles_montos = re.findall(r"\d{1,4}[.,]\d{2}", texto)
        montos = [parse_float(m) for m in posibles_montos]
        monto = max(montos) if montos else 0

    descripcion_lineas = []
    for linea in lineas:
        if re.search(r"[a-zA-Z]{3,}.*\d{1,4}[.,]\d{2}", linea):
            descripcion_lineas.append(linea.strip())

    descripcion = ', '.join(descripcion_lineas[:3]) if descripcion_lineas else 'Sin descripción'

    fecha = datetime.today().strftime('%Y-%m-%d')

    return fecha, descripcion, monto 

def procesar_imagen(nombre_archivo):
    ruta = os.path.join(IMAGENES_PATH, nombre_archivo)
    imagen = Image.open(ruta)
    texto = pytesseract.image_to_string(imagen, lang='eng+spa')

    fecha, descripcion, monto = extraer_info(texto)

    cursor.execute("INSERT INTO gastos (fecha, descripcion, monto, fuente_imagen) VALUES (?, ?, ?, ?)",
                   (fecha,  descripcion, monto, nombre_archivo))
    conn.commit()

    print(f'\n✅ Gasto registrado desde {nombre_archivo}')
    print(f"   Fecha: {fecha}")
    print(f"   Descripción: {descripcion}")
    print(f"   Monto: ${monto:.2f}")

if __name__ == '__main__':
    archivos = os.listdir(IMAGENES_PATH)
    imagenes = [f for f in archivos if f.lower().endswith(('.png', '.jpg', '.jpeg'))]

    for img in imagenes:
        procesar_imagen(img)

    conn.close()