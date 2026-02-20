from app import create_app, db
from sqlalchemy import text

app = create_app()
with app.app_context():
    # 1. Agregamos la columna de roles
    db.session.execute(text("ALTER TABLE users ADD COLUMN rol VARCHAR(20) DEFAULT 'empleado';"))
    
    # 2. Convertimos a todos los usuarios actuales en Administradores
    db.session.execute(text("UPDATE users SET rol = 'admin';"))
    
    db.session.commit()
    print("✅ Columna 'rol' creada y usuario actual elevado a Admin.")