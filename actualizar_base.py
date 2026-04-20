from app import create_app, db
from sqlalchemy import text

# Inicializamos la app para tener contexto de la base de datos
app = create_app()

def migrar_base_de_datos():
    with app.app_context():
        try:
            print("⏳ 0/4 - Creando tabla 'auditoria_logs'...")
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS auditoria_logs (
                    id SERIAL PRIMARY KEY,
                    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    usuario VARCHAR(100) NOT NULL,
                    accion VARCHAR(100) NOT NULL,
                    detalle TEXT
                );
            """))

            print("⏳ 1/4 - Verificando tabla 'historial_aumentos'...")
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS historial_aumentos (
                    id SERIAL PRIMARY KEY,
                    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    descripcion VARCHAR(255) NOT NULL,
                    casas_afectadas INTEGER NOT NULL,
                    mes_desde INTEGER,
                    anio_desde INTEGER
                );
            """))

            print("⏳ 2/4 - Verificando columnas en 'abonos_historicos' (Pago en Cascada)...")
            db.session.execute(text("ALTER TABLE abonos_historicos ADD COLUMN IF NOT EXISTS transaccion_id VARCHAR(100);"))
            db.session.execute(text("ALTER TABLE abonos_historicos ADD COLUMN IF NOT EXISTS detalle_pagos TEXT;"))

            print("⏳ 3/4 - Verificando columnas en 'abonos_historicos' (Monto Pagado USD)...")
            db.session.execute(text("ALTER TABLE abonos_historicos ADD COLUMN IF NOT EXISTS monto_pagado_usd NUMERIC(10,2);"))
            db.session.execute(text("ALTER TABLE abonos_historicos ADD COLUMN IF NOT EXISTS cotizacion_usd NUMERIC(10,2);"))

            print("⏳ 4/4 - Verificando columnas en 'casas' (Email y Teléfono)...")
            db.session.execute(text("ALTER TABLE casas ADD COLUMN IF NOT EXISTS telefono VARCHAR(50);"))
            db.session.execute(text("ALTER TABLE casas ADD COLUMN IF NOT EXISTS email VARCHAR(120);"))

            print("⏳ 5/5 - Verificando columnas de saldo en 'grupos_clientes'...")
            db.session.execute(text("ALTER TABLE grupos_clientes ADD COLUMN IF NOT EXISTS saldo_a_favor NUMERIC(10,2) NOT NULL DEFAULT 0;"))
            db.session.execute(text("ALTER TABLE grupos_clientes ADD COLUMN IF NOT EXISTS saldo_desde_mes INTEGER;"))
            db.session.execute(text("ALTER TABLE grupos_clientes ADD COLUMN IF NOT EXISTS saldo_desde_anio INTEGER;"))

            # Guardamos los cambios
            db.session.commit()
            print("✅ ¡Base de datos migrada con éxito!")

        except Exception as e:
            db.session.rollback()
            print(f"❌ ERROR al migrar la base de datos: {str(e)}")

if __name__ == "__main__":
    migrar_base_de_datos()