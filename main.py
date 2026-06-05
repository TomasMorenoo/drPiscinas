import os
import time
from datetime import datetime, timedelta, timezone

# Forzamos el entorno a UTC-3 (Argentina)
os.environ['TZ'] = 'Etc/GMT+3' 
try:
    if hasattr(time, 'tzset'):
        time.tzset()
except:
    pass

from app import create_app, db
import app.models 

app = create_app()

# Inyectamos una función global para que Jinja (el HTML) siempre tenga la hora correcta
@app.context_processor
def inject_now():
    # Argentina es UTC-3
    return {'now': datetime.now(timezone(timedelta(hours=-3)))}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, reloader_type='stat')