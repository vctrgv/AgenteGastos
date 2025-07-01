# Imagen base de Python
FROM python:3.11

# Establecer directorio de trabajo
WORKDIR /app

# Copiar los archivos necesarios
COPY requirements.txt .

# Instalar pytesseract
RUN apt-get update && apt-get install -y tesseract-ocr && rm -rf /var/lib/apt/lists/*

# Instalar dependencias
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar el resto del proyecto
COPY . .

# Exponer el puerto para documentación (opcional, informativo)
EXPOSE 8000

# Comando para iniciar FastAPI
CMD ["uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8000"]
