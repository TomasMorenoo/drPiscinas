FROM python:3.9-slim

# Instalamos dependencias para conectar con Postgres
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /sistema

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos todo el código fuente
COPY . .

CMD ["python", "main.py"]