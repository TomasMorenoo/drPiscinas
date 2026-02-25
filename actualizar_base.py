from app import create_app, db
from sqlalchemy import text

app = create_app()
with app.app_context():
    # Agregamos la columna de pago exacto al historial de cada mes
    db.session.execute(text("ALTER TABLE abonos_historicos ADD COLUMN monto_pagado DOUBLE PRECISION DEFAULT 0;"))
    db.session.commit()
    print("✅ Columna 'monto_pagado' agregada. Lista para pagos en cuotas.")