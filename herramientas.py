from app import create_app, db
from app.models.casa import Casa
from sqlalchemy.exc import IntegrityError

app = create_app()

def eliminar_cliente():
    id_input = input("\n👉 Ingresá el ID exacto del cliente a eliminar: ")
    
    if not id_input.isdigit():
        print("❌ El ID debe ser un número.")
        return
    
    casa = Casa.query.get(int(id_input))
    if not casa:
        print(f"❌ No se encontró ningún cliente con el ID {id_input} en la base de datos.")
        return
    
    # Intenta buscar el nombre, si falla usa el numero
    nombre_mostrar = casa.nombre_formateado() if hasattr(casa, 'nombre_formateado') else casa.numero
    
    print(f"\n⚠️ Estás a punto de eliminar a: {nombre_mostrar} (ID: {casa.id})")
    confirm = input("¿Estás seguro de que querés borrarlo para siempre? (s/n): ").lower()
    
    if confirm == 's':
        try:
            db.session.delete(casa)
            db.session.commit()
            print("✅ Cliente eliminado correctamente.")
        except IntegrityError:
            db.session.rollback()
            print("❌ ERROR DE SEGURIDAD: No podés eliminar este cliente porque ya tiene visitas históricas asociadas.")
            print("Para borrarlo, primero tendrías que borrar sus visitas del sistema.")
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error al eliminar: {e}")
    else:
        print("Operación cancelada. El cliente está a salvo.")

def resetear_precios():
    print("\n⚠️ ATENCIÓN: Esto pondrá el 'Abono Base Mensual' de TODOS tus clientes a $0.")
    confirm = input("¿Estás 100% seguro de querer borrar todos los precios? (s/n): ").lower()
    
    if confirm == 's':
        try:
            casas = Casa.query.all()
            for casa in casas:
                casa.precio_base = 0.0
            
            db.session.commit()
            print(f"✅ ¡Éxito! Se resetearon a $0 los precios de {len(casas)} clientes.")
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error al resetear precios: {e}")
    else:
        print("Operación cancelada. Los precios no se modificaron.")

def menu():
    while True:
        print("\n========================================")
        print("   🛠️  HERRAMIENTAS DE LIMPIEZA DB       ")
        print("========================================")
        print("[1] Eliminar un cliente específico por su ID")
        print("[2] Poner TODOS los precios de abono en $0")
        print("[0] Salir")
        
        opcion = input("\n👉 Elegí una opción (0, 1 o 2): ")
        
        if opcion == '1':
            with app.app_context():
                eliminar_cliente()
        elif opcion == '2':
            with app.app_context():
                resetear_precios()
        elif opcion == '0':
            print("Saliendo de las herramientas...")
            break
        else:
            print("❌ Opción inválida.")

if __name__ == "__main__":
    menu()