import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

def obtener_engine():
    # Intenta primero Local (tu PC) y luego 'db' (Docker/VPS)
    url_local = "postgresql://drPiscinas:administrador@localhost:5432/drPiscinas_db"
    url_docker = "postgresql://drPiscinas:administrador@db:5432/drPiscinas_db"
    
    for url in [url_local, url_docker]:
        try:
            engine = create_engine(url)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print(f"✅ Conectado a: {url.split('@')[1]}")
            return engine
        except Exception:
            continue
    return None

def ejecutar_migracion():
    engine = obtener_engine()
    if not engine:
        print("🔴 ERROR: No se pudo conectar a la base de datos. ¿Está prendido el Postgres?")
        return

    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        print("🚀 Iniciando actualización de tablas...")

        # 1. Crear la tabla de grupos
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS grupos_clientes (
                id SERIAL PRIMARY KEY,
                nombre VARCHAR(100) NOT NULL
            );
        """))
        print("1️⃣ Tabla 'grupos_clientes' verificada/creada.")

        # 2. Agregar columna grupo_id a la tabla casas
        # Usamos un bloque try/except específico por si la columna ya existe en Postgres
        try:
            session.execute(text("ALTER TABLE casas ADD COLUMN grupo_id INTEGER;"))
            session.commit()
            print("2️⃣ Columna 'grupo_id' agregada a la tabla 'casas'.")
        except Exception:
            session.rollback()
            print("2️⃣ La columna 'grupo_id' ya existía, saltando...")

        # 3. Crear la relación (Llave foránea)
        try:
            session.execute(text("""
                ALTER TABLE casas 
                ADD CONSTRAINT fk_casa_grupo 
                FOREIGN KEY (grupo_id) 
                REFERENCES grupos_clientes(id);
            """))
            session.commit()
            print("3️⃣ Relación de base de datos creada.")
        except Exception:
            session.rollback()
            print("3️⃣ La relación ya existía, saltando...")

        print("\n✅ TODO LISTO. Ya podés entrar al Dashboard sin errores.")

    except Exception as e:
        session.rollback()
        print(f"🔴 ERROR CRÍTICO: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    ejecutar_migracion()