# ejecutar en consola: python actualizar_pago.py
from app import create_app, db
from sqlalchemy import text
app = create_app()
with app.app_context():
    db.session.execute(text("ALTER TABLE abonos_historicos ADD COLUMN pagado BOOLEAN DEFAULT FALSE;"))
    db.session.execute(text("ALTER TABLE casas ADD COLUMN nombre_cliente VARCHAR(100);"))
    db.session.execute(text("ALTER TABLE casas ADD COLUMN telefono VARCHAR(50);"))
    db.session.execute(text("ALTER TABLE abonos_historicos ADD COLUMN mensaje_enviado BOOLEAN DEFAULT FALSE;"))
    db.session.commit()
    print("✅ Columnas de teléfono y cliente agregadas correctamente.")
    print("✅ Columna de pago agregada correctamente.")
    print("todas las columnas creadas exitosamente")
