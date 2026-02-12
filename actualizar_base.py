from app import create_app, db
from sqlalchemy import text, inspect

app = create_app()

with app.app_context():
    inspector = inspect(db.engine)
    tablas = inspector.get_table_names()
    print(f"📋 Tablas en DB: {tablas}")

    # --- ARREGLO 1: VISIT_PRODUCTS (El error que tenés ahora) ---
    tabla_vp = next((t for t in tablas if t.lower() == 'visit_products'), None)
    
    if tabla_vp:
        print(f"🎯 Corrigiendo tabla '{tabla_vp}'...")
        # Agregamos precio_unitario
        try:
            db.session.execute(text(f"ALTER TABLE {tabla_vp} ADD COLUMN precio_unitario DOUBLE PRECISION;"))
            db.session.commit()
            print("✅ Columna 'precio_unitario' agregada.")
            
            # Llenamos con el precio actual para que no queden en NULL
            # Asumiendo que tu tabla de productos se llama 'products'
            db.session.execute(text(f"""
                UPDATE {tabla_vp} vp 
                SET precio_unitario = p.precio 
                FROM products p 
                WHERE vp.product_id = p.id AND vp.precio_unitario IS NULL;
            """))
            db.session.commit()
            print("✅ Precios históricos sincronizados con el catálogo actual.")
        except Exception as e:
            db.session.rollback()
            print(f"ℹ️ Info VisitProducts: {e}")

    # --- ARREGLO 2: CASAS (Para futuros aumentos) ---
    tabla_casa = next((t for t in tablas if t.lower() in ['casa', 'casas']), None)
    
    if tabla_casa:
        print(f"🎯 Corrigiendo tabla '{tabla_casa}'...")
        try:
            db.session.execute(text(f"ALTER TABLE {tabla_casa} ADD COLUMN precio_anterior DOUBLE PRECISION;"))
            db.session.commit()
            print("✅ Columna 'precio_anterior' agregada.")
        except Exception as e:
            db.session.rollback()
            print(f"ℹ️ Info Casas: {e}")

    print("\n🚀 Proceso terminado. Reiniciá el contenedor de Flask.")