from app import create_app, db
from sqlalchemy import text

# Inicializamos la app para tener contexto de la base de datos
app = create_app()

def _run(sql, params=None):
    """Ejecuta un statement, hace commit, e imprime error sin abortar el resto."""
    try:
        db.session.execute(text(sql), params or {})
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"  WARN: {e}")


def migrar_base_de_datos():
    with app.app_context():
        print("Creando tabla auditoria_logs...")
        _run("""
            CREATE TABLE IF NOT EXISTS auditoria_logs (
                id SERIAL PRIMARY KEY,
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                usuario VARCHAR(100) NOT NULL,
                accion VARCHAR(100) NOT NULL,
                detalle TEXT
            );
        """)
        _run("ALTER TABLE auditoria_logs ADD COLUMN IF NOT EXISTS ip VARCHAR(45);")

        print("Creando tabla historial_aumentos...")
        _run("""
            CREATE TABLE IF NOT EXISTS historial_aumentos (
                id SERIAL PRIMARY KEY,
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                descripcion VARCHAR(255) NOT NULL,
                casas_afectadas INTEGER NOT NULL,
                mes_desde INTEGER,
                anio_desde INTEGER
            );
        """)

        print("Columnas abonos_historicos...")
        _run("ALTER TABLE abonos_historicos ADD COLUMN IF NOT EXISTS transaccion_id VARCHAR(100);")
        _run("ALTER TABLE abonos_historicos ADD COLUMN IF NOT EXISTS detalle_pagos TEXT;")
        _run("ALTER TABLE abonos_historicos ADD COLUMN IF NOT EXISTS monto_pagado_usd NUMERIC(10,2);")
        _run("ALTER TABLE abonos_historicos ADD COLUMN IF NOT EXISTS cotizacion_usd NUMERIC(10,2);")
        _run("ALTER TABLE abonos_historicos ADD COLUMN IF NOT EXISTS doble_instancia_enviada BOOLEAN NOT NULL DEFAULT FALSE;")

        print("Columnas casas...")
        _run("ALTER TABLE casas ADD COLUMN IF NOT EXISTS telefono VARCHAR(50);")
        _run("ALTER TABLE casas ADD COLUMN IF NOT EXISTS email VARCHAR(120);")
        _run("ALTER TABLE casas ADD COLUMN IF NOT EXISTS pausado BOOLEAN NOT NULL DEFAULT FALSE;")

        print("Columnas grupos_clientes...")
        _run("ALTER TABLE grupos_clientes ADD COLUMN IF NOT EXISTS saldo_a_favor NUMERIC(10,2) NOT NULL DEFAULT 0;")
        _run("ALTER TABLE grupos_clientes ADD COLUMN IF NOT EXISTS saldo_desde_mes INTEGER;")
        _run("ALTER TABLE grupos_clientes ADD COLUMN IF NOT EXISTS saldo_desde_anio INTEGER;")

        print("Tabla pausas...")
        _run("""
            CREATE TABLE IF NOT EXISTS pausas (
                id SERIAL PRIMARY KEY,
                casa_id INTEGER NOT NULL REFERENCES casas(id),
                desde DATE NOT NULL,
                hasta DATE
            );
        """)
        _run("ALTER TABLE pausas ADD COLUMN IF NOT EXISTS pausado_por VARCHAR(100);")

        print("Tabla plantillas_mensaje...")
        _run("""
            CREATE TABLE IF NOT EXISTS plantillas_mensaje (
                id SERIAL PRIMARY KEY,
                nombre VARCHAR(100) NOT NULL,
                activa BOOLEAN NOT NULL DEFAULT FALSE,
                creada_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                texto_intro_individual TEXT,
                label_al_dia VARCHAR(200),
                label_total VARCHAR(200),
                label_detalle VARCHAR(200),
                label_mantenimiento VARCHAR(200),
                label_productos VARCHAR(200),
                label_saldo_anterior VARCHAR(200),
                label_entregado VARCHAR(200),
                cierre VARCHAR(200),
                texto_intro_grupo TEXT,
                label_saldo_favor TEXT
            );
        """)
        _run("ALTER TABLE plantillas_mensaje ADD COLUMN IF NOT EXISTS template_individual TEXT;")
        _run("ALTER TABLE plantillas_mensaje ADD COLUMN IF NOT EXISTS template_grupo TEXT;")
        _run("ALTER TABLE plantillas_mensaje ADD COLUMN IF NOT EXISTS template_recordatorio TEXT;")
        _run("""
            INSERT INTO plantillas_mensaje (nombre, activa)
            SELECT 'Plantilla Default', TRUE
            WHERE NOT EXISTS (SELECT 1 FROM plantillas_mensaje);
        """)

        print("Indices...")
        _run("CREATE INDEX IF NOT EXISTS idx_abono_casa_mes_anio ON abonos_historicos (casa_id, mes, anio);")
        _run("CREATE INDEX IF NOT EXISTS idx_casa_activo ON casas (activo);")
        _run("CREATE INDEX IF NOT EXISTS idx_casa_grupo_id ON casas (grupo_id);")
        _run("CREATE INDEX IF NOT EXISTS idx_visit_casa_id ON visits (casa_id);")
        _run("CREATE INDEX IF NOT EXISTS idx_visit_fecha ON visits (fecha);")

        print("Tabla movimientos_stock...")
        _run("ALTER TABLE products ADD COLUMN IF NOT EXISTS stock_actual NUMERIC(10,2) NOT NULL DEFAULT 0;")
        _run("""
            CREATE TABLE IF NOT EXISTS movimientos_stock (
                id SERIAL PRIMARY KEY,
                product_id INTEGER NOT NULL REFERENCES products(id),
                tipo VARCHAR(20) NOT NULL,
                cantidad NUMERIC(10,2) NOT NULL,
                motivo VARCHAR(200),
                usuario VARCHAR(100),
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                visit_id INTEGER REFERENCES visits(id)
            );
        """)

        print("Saldo previo en grupos_clientes...")
        _run("ALTER TABLE grupos_clientes ADD COLUMN IF NOT EXISTS saldo_a_favor_previo NUMERIC(10,2);")
        _run("ALTER TABLE grupos_clientes ADD COLUMN IF NOT EXISTS saldo_desde_mes_previo INTEGER;")
        _run("ALTER TABLE grupos_clientes ADD COLUMN IF NOT EXISTS saldo_desde_anio_previo INTEGER;")

        print("ultimo_saldo_aplicado en grupos_clientes...")
        _run("ALTER TABLE grupos_clientes ADD COLUMN IF NOT EXISTS ultimo_saldo_aplicado NUMERIC(10,2);")

        print("Proporcional primer mes...")
        _run("ALTER TABLE casas ADD COLUMN IF NOT EXISTS dia_visita VARCHAR(20);")
        _run("ALTER TABLE casas ALTER COLUMN dia_visita TYPE VARCHAR(20) USING dia_visita::TEXT;")
        _run("ALTER TABLE casas ADD COLUMN IF NOT EXISTS proporcional_pendiente NUMERIC(10,2);")
        _run("ALTER TABLE abonos_historicos ADD COLUMN IF NOT EXISTS proporcional_anterior NUMERIC(10,2);")

        print("Fecha reactivacion...")
        _run("ALTER TABLE casas ADD COLUMN IF NOT EXISTS fecha_reactivacion TIMESTAMP;")

        print("Saldo a favor individual por casa...")
        _run("ALTER TABLE casas ADD COLUMN IF NOT EXISTS saldo_a_favor NUMERIC(10,2) DEFAULT 0;")

        print("Listo.")

if __name__ == "__main__":
    migrar_base_de_datos()