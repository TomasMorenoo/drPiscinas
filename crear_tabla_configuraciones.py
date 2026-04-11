"""
crear_tabla_configuraciones.py
================================
Script de migración que crea la tabla 'configuraciones' en la base de datos.

Usá este script UNA SOLA VEZ en producción después de hacer el deploy.
Es seguro correrlo varias veces: usa CREATE TABLE IF NOT EXISTS.

USO:
  python crear_tabla_configuraciones.py
"""

from dotenv import load_dotenv
load_dotenv()

from app import create_app, db
from app.models.configuracion import Configuracion

app = create_app()

with app.app_context():
    # Crea la tabla solo si no existe (no toca nada más)
    db.create_all()
    print("✅ Tabla 'configuraciones' verificada/creada correctamente.")
