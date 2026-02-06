# Usamos Python liviano
FROM python:3.9-slim

# Creamos una carpeta de trabajo en el contenedor
WORKDIR /sistema

# 1. Copiamos y instalamos las librerías primero (para que sea rápido)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2. Copiamos TU carpeta "app" adentro del contenedor
COPY app ./app

# 3. Le decimos a Docker: "Ejecutá el python que está dentro de la carpeta app"
CMD ["python", "app/main.py"]