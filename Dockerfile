# Usa una imagen base oficial de Python. Es ligera y segura.
FROM python:3.12-slim

WORKDIR /app


COPY requirements.txt 
RUN pip install --no-cache-dir -r requirements.txt

COPY .env .
COPY server.key .


COPY . .

ENV APP_MODULE app:app

CMD ["gunicorn", "--bind", "0.0.0.0:$PORT", "--workers", "1", "--threads", "8", "--timeout", "0", "app:app"]
