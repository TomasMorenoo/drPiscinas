import sys
import os

# Agregamos la carpeta actual al camino de búsqueda de Python
sys.path.append(os.getcwd())

# Intentamos importar la base de datos y la app
# Si tu instancia de Flask se crea con create_app(), usamos eso
try:
    from app import db, create_app
    app = create_app()
except ImportError:
    # Si no, intentamos la importación directa que tenías
    from app import app, db

from sqlalchemy import text

def actualizar_base():
    with app.app_context():
        try:
            print("🚀 Iniciando actualización de base de datos...")
            # Ejecutamos el comando SQL directo para agregar la columna
            db.session.execute(text("ALTER TABLE visits ADD COLUMN usuario_id INTEGER;"))
            db.session.commit()
            print("✅ ¡Éxito! Columna 'usuario_id' agregada a la tabla 'visits'.")
        except Exception as e:
            db.session.rollback()
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("ℹ️ La columna 'usuario_id' ya existe, no hace falta hacer nada.")
            else:
                print(f"❌ Error inesperado: {e}")

if __name__ == "__main__":
    actualizar_base()