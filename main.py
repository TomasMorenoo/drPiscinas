import os
import time

# Forzar la zona horaria de Argentina antes de cualquier otra cosa
os.environ['TZ'] = 'America/Argentina/Buenos_Aires'
try:
    time.tzset() # Este comando activa la zona horaria en sistemas Linux (VPS)
except AttributeError:
    # En Windows tzset no existe, pero en la VPS (Linux) es lo que aplica el cambio
    pass

from app import create_app, db
import app.models 

app = create_app()

if __name__ == '__main__':
    # Eliminamos el create_all de acá para que no cree bases SQLite accidentales
    app.run(host='0.0.0.0', port=5000, debug=True)