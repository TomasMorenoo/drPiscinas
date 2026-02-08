from app import create_app, db
from sqlalchemy import text, inspect

# 1. Iniciamos la aplicación
app = create_app()

with app.app_context():
    print("🔌 Conectando y buscando tablas...")
    
    # 2. Usamos el 'Inspector' para ver los nombres reales de las tablas
    inspector = inspect(db.engine)
    tablas_existentes = inspector.get_table_names()
    
    print(f"📋 Tablas encontradas en la base de datos: {tablas_existentes}")

    # 3. Decidimos cuál es la correcta
    nombre_tabla = None
    if 'casa' in tablas_existentes:
        nombre_tabla = 'casa'
    elif 'casas' in tablas_existentes:
        nombre_tabla = 'casas'
    elif 'Casa' in tablas_existentes:
        nombre_tabla = 'Casa'

    # 4. Ejecutamos la orden si encontramos la tabla
    if nombre_tabla:
        print(f"🎯 Tabla detectada: '{nombre_tabla}'. Agregando columna...")
        
        # Usamos el nombre real que encontramos
        sql = text(f"ALTER TABLE {nombre_tabla} ADD COLUMN precio_anterior DOUBLE PRECISION;")
        
        try:
            db.session.execute(sql)
            db.session.commit()
            print("✅ ÉXITO TOTAL: Columna 'precio_anterior' agregada.")
            print("   Ya podés usar la herramienta de aumentos.")
        except Exception as e:
            print(f"⚠️  {e}")
            print("   (Probablemente la columna ya existía).")
    else:
        print("❌ ERROR: No encontré ninguna tabla que parezca ser la de 'casas'.")
        print("   Revisá la lista que imprimí arriba para ver qué nombre tiene.")