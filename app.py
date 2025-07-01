from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import Response, HTMLResponse, StreamingResponse, FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import requests
from io import BytesIO, StringIO
from PIL import Image
import pytesseract 
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import re 
import sqlite3
import os 
import csv
import subprocess
from twilio.rest import Client
from pydantic import BaseModel

client = Client(TWILIO_ACCOUNT_SID,TWILIO_AUTH_TOKEN)

pytesseract.pytesseract.tesseract_cmd = r"D:\Tesseract-OCR\tesseract.exe"

app = FastAPI()
carpeta_static = os.path.join(os.getcwd(), "static")
app.mount("/static", StaticFiles(directory=carpeta_static), name="static")

class GastoEditado(BaseModel):
    fecha: str 
    descripcion: str 
    monto: float 

def interpretar_comando(texto):
    texto = texto.strip().lower()
    hoy = datetime.now().date()

    if texto == "gastos hoy":
        return hoy, hoy, "Gastos de hoy"

    if texto == "gastos semana":
        inicio = hoy - timedelta(days=hoy.weekday())
        return inicio, hoy, "Gastos de esta semana"

    if texto in ("total año", "gastos año"):
        inicio = datetime(hoy.year, 1, 1).date()
        return inicio, hoy, "Gastos del año"

    match_mes = re.match(r'(total|gastos)\s+([a-z]+)', texto)
    if match_mes:
        _, mes_nombre = match_mes.groups()
        meses = {
            'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
            'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
            'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12
        }
        if mes_nombre in meses:
            mes = meses[mes_nombre]
            inicio = datetime(hoy.year, mes, 1).date()
            fin = (inicio + relativedelta(months=1)) - timedelta(days=1)
            return inicio, fin, f"Gastos de {mes_nombre.capitalize()}"

    match_fecha = re.match(r'gastos (\d{4}-\d{2}-\d{2})', texto)
    if match_fecha:
        fecha = datetime.strptime(match_fecha.group(1), "%Y-%m-%d").date()
        return fecha, fecha, f"Gastos del {fecha}"

    return None, None, None

def obtener_total_gastos(celular, desde, hasta):
    conn = sqlite3.connect("gastos.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT SUM(monto) FROM gastos
        WHERE celular = ? AND eliminado = 0 AND fecha BETWEEN ? AND ?
    """, (celular, str(desde), str(hasta)))
    total = cursor.fetchone()[0] or 0
    conn.close()
    return total


def responder_mensaje(telefono, mensaje):
    client.messages.create(
        body=mensaje,
        from_='whatsapp:+14155238886',
        to=telefono
    )

def generar_descripcion_local(texto_ocr):
    prompt = """Del siguiente texto extraído de un ticket de compra, responde ÚNICAMENTE con una descripción corta del tipo de gasto. No seas conversacional. Usa máximo 6 palabras.

        Ejemplos:
        - Compra supermercado
        - Pago con tarjeta débito
        - Depósito BBVA
        - Gasolina
        - Farmacia
        - Restaurante

        TICKET:
        {}
        DESCRIPCIÓN:""".format(texto_ocr.strip())

    try:
        result = subprocess.run(
            [r'C:\Users\icecr\AppData\Local\Programs\Ollama\ollama.exe','run','llama3'],
            input=prompt,
            capture_output=True,
            timeout=60,
            encoding='utf-8',
            errors='ignore'
        )

        salida = result.stdout.strip()

        for linea in salida.splitlines():
            linea = linea.strip()
            if 3 <= len(linea) <= 60 and not linea.lower().startswith('ticket'):
                return linea 

        return 'Descripción no detectada'
    
    except subprocess.TimeoutExpired:
        print("❌ Error: Ollama se tardó demasiado (timeout).")
        return "Descripción no detectada"
    except Exception as e:
        print("❌ Error con modelo local:", e)
        return "Descripción no detectada"

def normalizar_monto(raw):
    raw = raw.replace(" ", "").replace("$", "").replace("o", "0").replace("l", "1")
    raw = raw.replace(",", "")
    try:
        return float(raw)
    except:
        return 0.0

def parse_float(texto):
    texto = texto.strip()
    if ',' in texto and '.' not in texto:
        texto = texto.replace(',', '.')
    return float(re.sub(r'[^\d.]', '', texto))

def extraer_info(texto):
    lineas = texto.lower().splitlines()
    monto = 0.0
    fecha_extraida = None
    candidatos_total = []

    def normalizar_monto(raw):
        raw = raw.replace(" ", "").replace("$", "").replace("o", "0").replace("l", "1")
        raw = raw.replace(",", "")  # quitar separadores de miles
        try:
            return float(raw)
        except:
            return 0.0

    # 1. Priorizar líneas con "total"
    for i, linea in enumerate(lineas):
        if "total" in linea:
            matches = re.findall(r"\$\s?[\d.,]+", linea)
            # Si no se encontró monto en esa línea, intenta con la siguiente
            if not matches and i + 1 < len(lineas):
                matches = re.findall(r"\$\s?[\d.,]+", lineas[i + 1])

            for m in matches:
                val = normalizar_monto(m)
                if val >= 100:
                    candidatos_total.append(val)

    # 🛠️ 2. Fallback si no hay línea con "total"
    if not candidatos_total:
        matches = re.findall(r"\$\s?[\d.,]+", linea)  # busca patrones como "$1,999.00"
        for m in matches:
            val = normalizar_monto(m)
            if val > monto:
                monto = val
    else:
        monto = max(candidatos_total)

    # 📅 3. Fecha real si está escrita
    match_fecha = re.search(r"(?:fecha:?\s*)?([a-z]{3,9}[. ]?\s?\d{1,2},?\s?\d{4})", texto.lower())
    if match_fecha:
        try:
            fecha_extraida = datetime.strptime(match_fecha.group(1).replace(".", "").strip(), "%b %d, %Y").date()
        except:
            try:
                fecha_extraida = datetime.strptime(match_fecha.group(1).replace(".", "").strip(), "%B %d, %Y").date()
            except:
                pass

    fecha = fecha_extraida.strftime('%Y-%m-%d') if fecha_extraida else datetime.today().strftime('%Y-%m-%d')

    # 📝 4. Descripción heurística básica
    descripcion = "Gasto general"
    texto_limpio = texto.lower()
    if "restaurante" in texto_limpio or "propina" in texto_limpio:
        descripcion = "Comida en restaurante"
    elif "crocs" in texto_limpio:
        descripcion = "Compra en Crocs"
    elif "farmacia" in texto_limpio:
        descripcion = "Compra en farmacia"

    return fecha, descripcion, monto


@app.post('/webhook')
async def recibir_mensaje(request: Request):
    print("🛬 Webhook recibido")
    form = await request.form()
    mensaje = form.get('Body','')
    media_url = form.get('MediaUrl0',None)
    sender = form.get('From','').replace('whatsapp:','')
    numero_respuesta = f'whatsapp:{sender}'

    print("📩 Mensaje recibido desde:", sender)
    print("📨 Texto:", mensaje)
    print("📎 Media URL:", media_url)

    if media_url and media_url.startswith('http'):
        try:
            response = requests.get(media_url, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN))
            if response.status_code != 200:
                print(f"⚠️ Error al descargar la imagen: {response.status_code}")
                return Response(content="<Response><Message>Error al descargar la imagen</Message></Response>",
                                media_type="application/xml")
        
            imagen = Image.open(BytesIO(response.content))
            texto = pytesseract.image_to_string(imagen, lang='eng+spa')
            print("🧾 TEXTO OCR EXTRAÍDO:\n------------------------------")
            print(texto)
            fecha, _, monto = extraer_info(texto)
            print("🧮 Monto detectado final:", monto)
            descripcion = generar_descripcion_local(texto)

            conn = sqlite3.connect('gastos.db')
            cursor = conn.cursor()
            cursor.execute('INSERT INTO gastos (fecha, descripcion, monto, fuente_imagen, celular) VALUES (?, ?, ?, ?, ?)',
                        (fecha, descripcion, monto, media_url, sender))
            conn.commit()
            conn.close()

            print("✅ Gasto registrado correctamente")
            print(f"📅 {fecha}, 📝 {descripcion}, 💲{monto:.2f}")

            respuesta = f"""✅ Gasto registrado
                        📅 Fecha: {fecha}
                        📝 {descripcion}
                        💲 ${monto:.2f}"""
            responder_mensaje(numero_respuesta, respuesta)
            return Response(status_code=200)
        
        except Exception as e:
            responder_mensaje(numero_respuesta,f'❌ Error procesando imagen: {e}')
            return Response(status_code=200)
        
    else:
        texto_usuario = mensaje.strip().lower()
        if texto_usuario == 'ayuda':
            respuesta = (
                "📋 Comandos disponibles:\n"
                "• gastos hoy\n"
                "• gastos semana\n"
                "• total enero (o cualquier mes)\n"
                "• gastos 2025-06-01\n"
                "• total año\n"
                "• dashboard\n"
                "• ayuda"
            )
        elif texto_usuario == 'dashboard':
            url = f'https://https://academiccontrol.tail4abb85.ts.net/dashboard.html'
            respuesta = f'📊 Tu dashboard: {url}'
        else:
            desde, hasta, desc = interpretar_comando(texto_usuario)
            if desde and hasta:
                total = obtener_total_gastos(sender, desde, hasta)
                respuesta = (
                    f"🧾 {desc}\n"
                    f"🗓️ Del {desde} al {hasta}\n"
                    f"💰 Total: ${total:,.2f}"
                )
            else:
                respuesta = "❌ Comando no reconocido. Escribe *ayuda* para ver los comandos disponibles."
        responder_mensaje(numero_respuesta, respuesta)
        return Response(status_code=200)


@app.get('/dashboard', response_class=HTMLResponse)
async def mostrar_dashboard():
    html_path = os.path.join(os.path.dirname(__file__), 'dashboard.html')
    with open(html_path, 'r', encoding='utf-8') as f:
        return f.read()

app.add_middleware(
    CORSMiddleware, 
    allow_origins = ['*'],
    allow_methods = ['*'],
    allow_headers = ['*']
)

@app.get('/api/gastos')
async def obtener_gastos(
    desde: str = Query(None),
    hasta: str = Query(None), 
    celular: str = Query(None)
    ):
    conn = sqlite3.connect('gastos.db')
    cursor = conn.cursor()

    query = 'SELECT id, fecha, descripcion, monto FROM gastos'
    filtros = ['eliminado = 0']
    valores = []

    if desde: 
        filtros.append('fecha >= ?')
        valores.append(desde)
    if hasta:
        filtros.append('fecha <= ?')
        valores.append(hasta)
    if celular:
        filtros.append('celular = ?')
        valores.append(celular)
    
    if filtros:
        query += ' WHERE ' + ' AND '.join(filtros)

    query += ' ORDER BY fecha ASC'

    cursor.execute(query, valores)
    rows = cursor.fetchall()
    conn.close()

    return [{'id':r[0], 'fecha': r[1], 'descripcion': r[2], 'monto': r[3]} for r in rows]


@app.get('/api/gastos/csv')
async def exportar_csv(celular: str = Query(None)):
    conn =  sqlite3.connect('gastos.db')
    cursor = conn.cursor()

    query = 'SELECT fecha, descripcion, monto FROM gastos WHERE eliminado = 0'
    valores = []

    if celular:
        query += 'AND celular = ?'
        valores.append(celular)
    
    cursor.execute(query, valores)
    rows = cursor.fetchall()
    conn.close()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Fecha', 'Descripción', 'Monto'])
    writer.writerows(rows)
    output.seek(0)

    return StreamingResponse(output, media_type='text/csv', headers={
        'Content-Disposition': 'attatchment; filename=gastos.csv'
    })

@app.delete('/api/gastos/{id}')
async def eliminar_gasto(id: int):
    try:
        conn = sqlite3.connect('gastos.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE gastos SET eliminado = 1 WHERE id = ?', (id,))
        conn.commit()
        conn.close()
        return {'status': 'ok'}
    except Exception as e:
        print(f'❌ Error al marcar como eliminado: {e}')
        raise HTTPException(status_code=500, detail='Error al eliminar el gasto')
    
@app.get("/api/gastos/historial")
async def obtener_historial_completo(celular: str = Query(None)):
    conn = sqlite3.connect("gastos.db")
    cursor = conn.cursor()
    
    query = 'SELECT id, fecha, descripcion, monto, eliminado FROM gastos'
    valores = []

    if celular: 
        query += ' WHERE celular = ?'
        valores.append(celular)
    
    query += ' ORDER BY fecha DESC'

    cursor.execute(query, valores)
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "fecha": r[1],
            "descripcion": r[2],
            "monto": r[3],
            "eliminado": bool(r[4])
        }
        for r in rows
    ]

@app.post("/api/gastos/{id}/restaurar")
async def restaurar_gasto(id: int):
    try:
        conn = sqlite3.connect("gastos.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE gastos SET eliminado = 0 WHERE id = ?", (id,))
        conn.commit()
        conn.close()
        return {"status": "ok"}
    except Exception as e:
        print(f"❌ Error al restaurar gasto: {e}")
        raise HTTPException(status_code=500, detail="Error al restaurar el gasto.")

# Endpoint directo para servir el dashboard
@app.get("/dashboard.html")
def servir_dashboard():
    return FileResponse(os.path.join(carpeta_static, "dashboard.html"))

@app.get('/')
def redirigir_a_dashboard():
    return RedirectResponse(url='/dashboard.html')

@app.put('/api/gastos/{gasto_id}')
async def actualizar_gasto(gasto_id: int, datos: GastoEditado):
    conn = sqlite3.connect('gastos.db')
    cursor = conn.cursor()

    cursor.execute('SELECT id FROM gastos WHERE id = ?', (gasto_id,))
    if cursor.fetchone() is None:
        conn.close()
        raise HTTPException(status_code=404, detail='Gasto no encontrado')
    
    cursor.execute(""" 
        UPDATE gastos
        SET fecha = ?, descripcion = ?, monto = ?
        WHERE id = ?               
    """, (datos.fecha, datos.descripcion, datos.monto, gasto_id))

    conn.commit()
    conn.close()
    return {'mensaje': 'Gasto actualizado correctamente'}