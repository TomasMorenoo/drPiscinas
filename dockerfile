FROM python:3.9-slim

WORKDIR /sistema

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ACÁ EL CAMBIO: Copiamos TODO (el main.py y la carpeta app)
COPY . .

# ACÁ EL OTRO CAMBIO: Ya no buscamos en app/main.py, sino en main.py directo
CMD ["python", "main.py"]