# Usa una imagen base oficial de Python. Es ligera y segura.
FROM python:3.12-slim

# Establece el directorio de trabajo dentro del contenedor.
WORKDIR /app

# Copia el archivo de requerimientos e instala las dependencias.
# Se hace en un paso separado para aprovechar el caché de Docker.
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo el código de la aplicación al contenedor.
COPY . .

# Gunicorn necesita saber dónde está tu instancia de Flask.
# El formato es 'nombre_del_archivo:nombre_de_la_variable_app'.
ENV APP_MODULE app:app

# El puerto es proporcionado por Cloud Run a través de la variable de entorno PORT.
# Gunicorn se ejecutará en 0.0.0.0 para aceptar conexiones externas.
CMD exec gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 0 "$APP_MODULE"