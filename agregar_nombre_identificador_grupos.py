"""
agregar_nombre_identificador_grupos.py
=======================================
Migración que agrega la columna 'nombre_identificador' a la tabla grupos_clientes.

Correr UNA SOLA VEZ en producción después del deploy.
Es seguro correrlo varias veces: verifica si la columna ya existe antes de crearla.

USO:
  python agregar_nombre_identificador_grupos.py
"""

from dotenv import load_dotenv
load_dotenv()

from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    with db.engine.connect() as conn:
        # Verifica si la columna ya existe
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'grupos_clientes'
              AND column_name = 'nombre_identificador'
        """))
        existe = result.fetchone() is not None

    if existe:
        print("✅ La columna 'nombre_identificador' ya existe. No se hizo nada.")
    else:
        with db.engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE grupos_clientes ADD COLUMN nombre_identificador VARCHAR(100) NULL"
            ))
            conn.commit()
        print("✅ Columna 'nombre_identificador' agregada a grupos_clientes correctamente.")
