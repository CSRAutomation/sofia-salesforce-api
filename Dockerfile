# Usa una imagen base oficial de Python. Es ligera y segura.
FROM python:3.12-slim

WORKDIR /app


# Copia solo el archivo de requerimientos primero para aprovechar el cache de capas de Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ahora copia el resto de los archivos de la aplicación (incluyendo .env y server.key)
COPY . .

CMD ["gunicorn", "--bind", "0.0.0.0:$PORT", "--workers", "1", "--threads", "8", "--timeout", "0", "app:app"]
