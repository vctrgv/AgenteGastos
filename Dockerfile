# Imagen base de Python
FROM python:3.11

# Establecer directorio de trabajo
WORKDIR /app

# Copiar los archivos necesarios
COPY requirements.txt .

# Instalar dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del proyecto
COPY . .

# Comando para iniciar FastAPI
CMD ["uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8000"]
