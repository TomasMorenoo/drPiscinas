# script_crear_abonos.py
from app import create_app, db
from app.models.abono_historico import AbonoHistorico

app = create_app()
with app.app_context():
    # Esto le dice a SQLAlchemy que cree solo las tablas que faltan
    db.create_all()
    print("✅ Tabla abonos_historicos creada exitosamente.")