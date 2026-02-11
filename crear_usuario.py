from app import create_app, db
from app.models.user import User
import sys

# Inicializamos la app para tener acceso a la DB
app = create_app()

def crear_admin():
    with app.app_context():
        # 1. Crear las tablas si no existen (por si borraste la DB)
        db.create_all()

        print("--- CREACIÓN DE USUARIO ADMINISTRADOR ---")
        username = input("Ingrese nombre de usuario: ").strip()
        password = input("Ingrese contraseña: ").strip()

        if not username or not password:
            print("❌ Error: Usuario y contraseña son obligatorios.")
            return

        # 2. Verificar si ya existe
        usuario_existente = User.query.filter_by(username=username).first()
        if usuario_existente:
            print(f"⚠️  El usuario '{username}' ya existe.")
            
            # Opcional: ¿Querés cambiarle la clave al existente?
            cambiar = input("¿Desea actualizar la contraseña de este usuario? (s/n): ")
            if cambiar.lower() == 's':
                usuario_existente.set_password(password)
                db.session.commit()
                print("✅ Contraseña actualizada correctamente.")
            return

        # 3. Crear nuevo usuario
        nuevo_usuario = User(username=username)
        nuevo_usuario.set_password(password) # Esto la encripta
        
        db.session.add(nuevo_usuario)
        db.session.commit()
        
        print(f"✅ ¡ÉXITO! Usuario '{username}' creado.")
        print("Ahora podés iniciar sesión en /login")

if __name__ == "__main__":
    crear_admin()